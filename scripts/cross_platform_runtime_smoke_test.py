from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from synkraken import cli_main
from synkraken.runtime_service import (
    FutureWindowsRuntimeService,
    LinuxRuntimeService,
    MacOSRuntimeService,
    RuntimeServiceError,
)


class FakeRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.active = False

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        if command[:3] == ["systemctl", "--user", "is-active"]:
            return subprocess.CompletedProcess(command, 0 if self.active else 3, "active\n" if self.active else "inactive\n", "")
        if command[:2] == ["launchctl", "print"]:
            return subprocess.CompletedProcess(command, 0 if self.active else 113, "", "")
        if "start" in command or "restart" in command or "kickstart" in command or "bootstrap" in command:
            self.active = True
        if "stop" in command or "bootout" in command:
            self.active = False
        return subprocess.CompletedProcess(command, 0, "", "")


def assert_true(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def test_linux_service(root: Path, config_path: Path) -> None:
    runner = FakeRunner()
    service = LinuxRuntimeService(runner=runner, home=root)
    service.install(config_path)
    unit = service.unit_path.read_text(encoding="utf-8")
    assert_true("Restart=always" in unit, "systemd service must recover automatically")
    assert_true(str(config_path) in unit, "systemd service must use the selected config")
    assert_true(any(command[2:4] == ["enable", "--now"] for command in runner.commands), "install must enable and start systemd service")
    runner.active = True
    assert_true(service.status().running, "systemd status must report active service")
    service.uninstall()
    assert_true(not service.unit_path.exists(), "systemd uninstall must remove unit")


def test_macos_service(root: Path, config_path: Path) -> None:
    runner = FakeRunner()
    service = MacOSRuntimeService(runner=runner, home=root, uid=501)
    service.install(config_path)
    with service.plist_path.open("rb") as handle:
        payload = plistlib.load(handle)
    assert_true(payload["Label"] == "com.synkraken.daemon", "LaunchAgent label mismatch")
    assert_true(payload["RunAtLoad"] is True and payload["KeepAlive"] is True, "LaunchAgent must start and recover automatically")
    assert_true(payload["ProgramArguments"][-1] == str(config_path.resolve()), "LaunchAgent config path mismatch")
    verbs = [command[1] for command in runner.commands if command and command[0] == "launchctl"]
    for verb in ("bootstrap", "enable", "kickstart"):
        assert_true(verb in verbs, f"LaunchAgent install must call launchctl {verb}")
    runner.active = True
    assert_true(service.status().running, "LaunchAgent status must report loaded service")
    service.uninstall()
    assert_true(not service.plist_path.exists(), "LaunchAgent uninstall must remove plist")


def test_windows_contract(config_path: Path) -> None:
    service = FutureWindowsRuntimeService()
    assert_true(not service.status().installed, "Windows service must not claim to be installed")
    try:
        service.install(config_path)
    except RuntimeServiceError as exc:
        assert_true("not implemented" in str(exc), "Windows error must state implementation status")
    else:
        raise AssertionError("Windows install must not fake success")


def test_cli_recovery() -> None:
    class Service:
        def recover(self) -> bool:
            return True

    checks = iter([False, True])
    with patch.object(cli_main, "_wait_for_daemon_health", side_effect=lambda *_args, **_kwargs: next(checks)), patch.object(
        cli_main, "runtime_service_for_platform", return_value=Service()
    ):
        output = StringIO()
        with redirect_stdout(output):
            ok = cli_main.recover_runtime("http://127.0.0.1:9460")
    assert_true(ok, "CLI recovery must succeed after service recovery")
    assert_true("Recovery succeeded" in output.getvalue(), "CLI recovery must report success")


def test_install_and_uninstall(config_path: Path) -> None:
    class Service:
        platform_name = "Test OS"
        uninstalled = False

        def install(self, path: Path) -> None:
            assert_true(path == config_path, "install must receive selected config")

        def uninstall(self) -> None:
            self.uninstalled = True

    service = Service()
    with patch.object(cli_main, "runtime_service_for_platform", return_value=service), patch.object(
        cli_main, "_wait_for_daemon_health", return_value=True
    ):
        assert_true(cli_main.install_runtime(config_path, "http://127.0.0.1:9460", 2) == 0, "healthy install must succeed")
        assert_true(cli_main.uninstall_runtime() == 0, "uninstall must succeed")
    with patch.object(cli_main, "runtime_service_for_platform", return_value=service), patch.object(
        cli_main, "_wait_for_daemon_health", return_value=False
    ):
        assert_true(cli_main.install_runtime(config_path, "http://127.0.0.1:9460", 2) == 1, "unhealthy install must fail")
    assert_true(config_path.exists(), "uninstall must preserve config")
    assert_true(service.uninstalled, "uninstall must remove runtime integration")


def test_status_output() -> None:
    class Service:
        def status(self):
            return type("Status", (), {"platform": "macOS", "installed": True, "running": True})()

    health = {"ok": True, "started_at": "2026-06-07T10:00:00+00:00"}
    with patch.object(cli_main, "runtime_service_for_platform", return_value=Service()), patch.object(
        cli_main, "get_json", return_value=health
    ):
        output = StringIO()
        with redirect_stdout(output):
            result = cli_main.print_runtime_status("http://127.0.0.1:9460")
    rendered = output.getvalue()
    assert_true(result == 0, "healthy status must succeed")
    for expected in ("Platform:   macOS", "Service:    Running", "Health:     Healthy", "Uptime:", "Daemon URL:"):
        assert_true(expected in rendered, f"status output missing {expected}")


def test_doctor(root: Path, config_path: Path) -> None:
    db_path = root / "data" / "synkraken.db"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["storage"] = {"sqlite_path": str(db_path)}
    config["server"] = {"host": "127.0.0.1", "port": 0}
    config_path.write_text(json.dumps(config), encoding="utf-8")

    class Service:
        def status(self):
            return type("Status", (), {"installed": True, "running": True, "detail": "running"})()

    class Socket:
        def bind(self, address: tuple[str, int]) -> None:
            assert_true(address == ("127.0.0.1", 0), "doctor must probe the configured port")

        def close(self) -> None:
            return

    with patch.object(cli_main, "runtime_service_for_platform", return_value=Service()), patch.object(
        cli_main, "_wait_for_daemon_health", return_value=False
    ), patch.object(cli_main.socket, "socket", return_value=Socket()):
        output = StringIO()
        with redirect_stdout(output):
            result = cli_main.doctor_runtime(config_path, "http://127.0.0.1:9460")
    assert_true(result == 0, f"doctor must pass a valid isolated installation:\n{output.getvalue()}")
    assert_true("Runtime service" in output.getvalue() and "Database" in output.getvalue(), "doctor output is incomplete")


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        config_path = root / "config.local.json"
        config_path.write_text(json.dumps({"storage": {"sqlite_path": "data/test.db"}, "adapters": {"test": {"enabled": True}}}), encoding="utf-8")
        test_linux_service(root / "linux", config_path)
        test_macos_service(root / "mac", config_path)
        test_windows_contract(config_path)
        test_cli_recovery()
        test_install_and_uninstall(config_path)
        test_status_output()
        test_doctor(root, config_path)
    print("cross-platform runtime smoke test: PASS")


if __name__ == "__main__":
    main()

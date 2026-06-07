from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
from typing import Callable


SERVICE_LABEL = "com.synkraken.daemon"
SYSTEMD_UNIT = "synkraken.service"
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(slots=True)
class RuntimeServiceStatus:
    platform: str
    installed: bool
    running: bool
    detail: str = ""


class RuntimeServiceError(RuntimeError):
    pass


class RuntimeService(ABC):
    platform_name = "Unknown"

    def __init__(self, *, runner: CommandRunner = subprocess.run) -> None:
        self._runner = runner

    def _run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return self._runner(command, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            raise RuntimeServiceError(f"Required platform service command was not found: {command[0]}") from exc

    @abstractmethod
    def install(self, config_path: Path) -> None:
        raise NotImplementedError

    @abstractmethod
    def uninstall(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError

    def restart(self) -> None:
        self.stop()
        self.start()

    @abstractmethod
    def status(self) -> RuntimeServiceStatus:
        raise NotImplementedError

    def recover(self) -> bool:
        state = self.status()
        if not state.installed:
            return False
        if not state.running:
            self.start()
        return True


class LinuxRuntimeService(RuntimeService):
    platform_name = "Linux"

    def __init__(self, *, runner: CommandRunner = subprocess.run, home: Path | None = None) -> None:
        super().__init__(runner=runner)
        root = home or Path.home()
        self.unit_path = Path(os.environ.get("XDG_CONFIG_HOME", root / ".config")) / "systemd" / "user" / SYSTEMD_UNIT

    def _systemctl(self, *args: str, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
        result = self._run(["systemctl", "--user", *args])
        if result.returncode and not allow_failure:
            raise RuntimeServiceError((result.stderr or result.stdout or "systemd operation failed").strip())
        return result

    def install(self, config_path: Path) -> None:
        config_path = config_path.resolve()
        self.unit_path.parent.mkdir(parents=True, exist_ok=True)
        command = " ".join(_systemd_quote(value) for value in _daemon_command(config_path))
        content = (
            "[Unit]\n"
            "Description=SynKraken runtime\n"
            "After=network-online.target\n"
            "Wants=network-online.target\n\n"
            "[Service]\n"
            "Type=simple\n"
            f"WorkingDirectory={_systemd_quote(str(config_path.parent))}\n"
            f"ExecStart={command}\n"
            "Restart=always\n"
            "RestartSec=5\n\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        )
        self.unit_path.write_text(content, encoding="utf-8")
        self._systemctl("daemon-reload")
        self._systemctl("enable", "--now", SYSTEMD_UNIT)

    def uninstall(self) -> None:
        self._systemctl("disable", "--now", SYSTEMD_UNIT, allow_failure=True)
        self.unit_path.unlink(missing_ok=True)
        self._systemctl("daemon-reload", allow_failure=True)
        self._systemctl("reset-failed", SYSTEMD_UNIT, allow_failure=True)

    def start(self) -> None:
        self._systemctl("start", SYSTEMD_UNIT)

    def stop(self) -> None:
        self._systemctl("stop", SYSTEMD_UNIT)

    def restart(self) -> None:
        self._systemctl("restart", SYSTEMD_UNIT)

    def status(self) -> RuntimeServiceStatus:
        installed = self.unit_path.exists()
        if not installed:
            return RuntimeServiceStatus(self.platform_name, False, False, "Runtime is not installed")
        result = self._systemctl("is-active", SYSTEMD_UNIT, allow_failure=True)
        running = result.returncode == 0 and result.stdout.strip() == "active"
        detail = result.stdout.strip() or result.stderr.strip()
        return RuntimeServiceStatus(self.platform_name, True, running, detail)


class MacOSRuntimeService(RuntimeService):
    platform_name = "macOS"

    def __init__(
        self,
        *,
        runner: CommandRunner = subprocess.run,
        home: Path | None = None,
        uid: int | None = None,
    ) -> None:
        super().__init__(runner=runner)
        root = home or Path.home()
        self.home = root
        self.plist_path = root / "Library" / "LaunchAgents" / f"{SERVICE_LABEL}.plist"
        self.uid = os.getuid() if uid is None else uid
        self.domain = f"gui/{self.uid}"
        self.target = f"{self.domain}/{SERVICE_LABEL}"

    def _launchctl(self, *args: str, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
        result = self._run(["launchctl", *args])
        if result.returncode and not allow_failure:
            raise RuntimeServiceError((result.stderr or result.stdout or "LaunchAgent operation failed").strip())
        return result

    def install(self, config_path: Path) -> None:
        config_path = config_path.resolve()
        self.plist_path.parent.mkdir(parents=True, exist_ok=True)
        logs = self.home / "Library" / "Logs" / "SynKraken"
        logs.mkdir(parents=True, exist_ok=True)
        payload = {
            "Label": SERVICE_LABEL,
            "ProgramArguments": _daemon_command(config_path),
            "WorkingDirectory": str(config_path.parent),
            "RunAtLoad": True,
            "KeepAlive": True,
            "ThrottleInterval": 5,
            "StandardOutPath": str(logs / "runtime.log"),
            "StandardErrorPath": str(logs / "runtime-error.log"),
        }
        with self.plist_path.open("wb") as handle:
            plistlib.dump(payload, handle, sort_keys=False)
        self._launchctl("bootout", self.target, allow_failure=True)
        self._launchctl("bootstrap", self.domain, str(self.plist_path))
        self._launchctl("enable", self.target)
        self._launchctl("kickstart", "-k", self.target)

    def uninstall(self) -> None:
        self._launchctl("bootout", self.target, allow_failure=True)
        self._launchctl("disable", self.target, allow_failure=True)
        self.plist_path.unlink(missing_ok=True)

    def start(self) -> None:
        if not self.status().running:
            self._launchctl("bootstrap", self.domain, str(self.plist_path))
        self._launchctl("enable", self.target)
        self._launchctl("kickstart", "-k", self.target)

    def stop(self) -> None:
        self._launchctl("bootout", self.target)

    def restart(self) -> None:
        state = self.status()
        if not state.installed:
            raise RuntimeServiceError("SynKraken is not installed")
        if not state.running:
            self._launchctl("bootstrap", self.domain, str(self.plist_path))
        self._launchctl("enable", self.target)
        self._launchctl("kickstart", "-k", self.target)

    def status(self) -> RuntimeServiceStatus:
        installed = self.plist_path.exists()
        if not installed:
            return RuntimeServiceStatus(self.platform_name, False, False, "Runtime is not installed")
        result = self._launchctl("print", self.target, allow_failure=True)
        running = result.returncode == 0
        detail = "loaded" if running else (result.stderr.strip() or "not loaded")
        return RuntimeServiceStatus(self.platform_name, True, running, detail)


class FutureWindowsRuntimeService(RuntimeService):
    platform_name = "Windows"

    def _unsupported(self) -> None:
        raise RuntimeServiceError(
            "Windows runtime service support is not implemented yet. "
            "The service contract requires install, uninstall, start, stop, restart, and status operations."
        )

    def install(self, config_path: Path) -> None:
        self._unsupported()

    def uninstall(self) -> None:
        self._unsupported()

    def start(self) -> None:
        self._unsupported()

    def stop(self) -> None:
        self._unsupported()

    def status(self) -> RuntimeServiceStatus:
        return RuntimeServiceStatus(self.platform_name, False, False, "Runtime service support is planned")


def runtime_service_for_platform(
    platform: str | None = None,
    *,
    runner: CommandRunner = subprocess.run,
    home: Path | None = None,
) -> RuntimeService:
    current = platform or sys.platform
    if current.startswith("linux"):
        return LinuxRuntimeService(runner=runner, home=home)
    if current == "darwin":
        return MacOSRuntimeService(runner=runner, home=home)
    if current.startswith("win"):
        return FutureWindowsRuntimeService(runner=runner)
    raise RuntimeServiceError(f"Unsupported platform: {current}")


def parse_started_at(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def format_uptime(started_at: object) -> str:
    started = parse_started_at(started_at)
    if started is None:
        return "Unknown"
    seconds = max(0, int((datetime.now(timezone.utc) - started).total_seconds()))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def _daemon_command(config_path: Path) -> list[str]:
    return [sys.executable, "-m", "synkraken", "--config", str(config_path)]


def _systemd_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace(" ", "\\x20")

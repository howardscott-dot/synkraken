from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_DIR = ROOT / "docs" / "screenshots"
EXPECTED = [
    "canvas.png",
    "workforce.png",
    "rooms.png",
    "proposal-governance.png",
    "flight-recorder.png",
    "incident-centre.png",
]


def main() -> int:
    missing = [name for name in EXPECTED if not (SCREENSHOT_DIR / name).is_file()]
    if missing:
        print("console screenshot check: missing")
        for name in missing:
            print(f"- docs/screenshots/{name}")
        return 1
    print("console screenshot check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

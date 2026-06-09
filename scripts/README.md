# Scripts

SynKraken uses smoke tests instead of a pytest suite.

Active smoke tests should target:

- daemon API behavior
- CLI behavior
- TUI behavior
- Web Command Deck behavior
- adapter conformance
- future MCP tool contracts

`console_*_smoke_test.py` files are historical source checks for the retired
Tauri Console prototype. They are not part of the active release checklist.

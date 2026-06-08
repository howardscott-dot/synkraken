.PHONY: install run console test lint clean help

help:
	@echo "SynKraken Makefile"
	@echo ""
	@echo "  install    Install the daemon in editable mode (pip install -e .)"
	@echo "  run        Start the SynKraken daemon with example config"
	@echo "  console    Build and launch the Tauri Console app"
	@echo "  test       Run all tests"
	@echo "  lint       Run ruff linter"
	@echo "  clean      Remove build artifacts and __pycache__"

install:
	pip install -e ".[dev]"

run:
	synkraken run --config examples/config.example.json

console:
	cd apps/console/src-tauri && cargo build --release && cd ../..
	@echo "Binary: apps/console/src-tauri/target/release/synkraken-console"

test:
	pytest tests/ -v

lint:
	ruff check synkraken/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	cd apps/console/src-tauri && cargo clean 2>/dev/null || true
"""Shared pytest fixtures for the SynKraken suite."""
from __future__ import annotations

import sys
import base64
import os
from pathlib import Path
import pytest

# Allow `import synkraken` when running from a source checkout without install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def isolated_vault_key(monkeypatch):
    monkeypatch.setenv("SYNKRAKEN_VAULT_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())

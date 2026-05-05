"""Shared fixtures for pytest-mattermost tests."""

from __future__ import annotations

import pytest

# Enable the pytester fixture so we can spawn isolated pytest sessions.
pytest_plugins = ["pytester"]


_MM_ENV_VARS = (
    "MATTERMOST_URL",
    "MATTERMOST_TOKEN",
    "MATTERMOST_CHANNEL_ID",
    "MATTERMOST_WEBHOOK_URL",
    "MATTERMOST_VERIFY_SSL",
    "MATTERMOST_PROJECT",
    "MATTERMOST_BRANCH",
    "MATTERMOST_COMMIT",
    "MATTERMOST_RUN_URL",
)


@pytest.fixture(autouse=True)
def _clean_mattermost_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove any MATTERMOST_* env vars so tests run in a clean state."""
    for name in _MM_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

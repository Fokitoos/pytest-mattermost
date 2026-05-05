"""Pytest plugin that posts test run summaries to a Mattermost channel."""

import pytest

from .client import (
    AuthMethod,
    MattermostClient,
    MattermostConfig,
    MattermostPostError,
)
from .report import FailedTest, TestRunSummary, render_summary

__version__ = "0.1.0"

# Stash key for injecting extra metadata fields into the attachment.
# Populate it in your conftest.py:
#
#   from pytest_mattermost import METADATA_KEY
#
#   def pytest_configure(config):
#       config.stash[METADATA_KEY] = {"Environment": "staging", "Python": "3.12"}
#
METADATA_KEY: pytest.StashKey[dict[str, str]] = pytest.StashKey()

__all__ = [
    "AuthMethod",
    "FailedTest",
    "METADATA_KEY",
    "MattermostClient",
    "MattermostConfig",
    "MattermostPostError",
    "TestRunSummary",
    "__version__",
    "render_summary",
]

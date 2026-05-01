"""Pytest plugin that posts test run summaries to a Mattermost channel."""

from .client import (
    AuthMethod,
    MattermostClient,
    MattermostConfig,
    MattermostPostError,
)
from .report import FailedTest, TestRunSummary, render_summary

__version__ = "0.1.0"

__all__ = [
    "AuthMethod",
    "FailedTest",
    "MattermostClient",
    "MattermostConfig",
    "MattermostPostError",
    "TestRunSummary",
    "__version__",
    "render_summary",
]

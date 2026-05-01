"""Pytest plugin wires pytest hooks to the Mattermost reporter.

Registration happens automatically via the ``pytest11`` entry-point
(see ``pyproject.toml``).  Users only need to set the required
environment variables and optionally pass CLI flags.

CLI flags
---------
``--mattermost``          Enable reporting (off by default so local
                          runs stay silent).
``--mm-auth-method``      ``bot_token`` (default) or ``webhook``.
``--mm-on-failure-only``  Only post if the suite has failures.
"""

import os
import time

import pytest
from loguru import logger

from .client import AuthMethod, MattermostClient, MattermostConfig, MattermostPostError
from .report import FailedTest, TestRunSummary, render_summary


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register Mattermost related command-line options."""
    group = parser.getgroup("mattermost", "Mattermost test reporter")

    group.addoption(
        "--mattermost",
        action="store_true",
        default=False,
        help="Enable Mattermost reporting.",
    )
    group.addoption(
        "--mm-auth-method",
        default="bot_token",
        choices=["bot_token", "webhook"],
        help="Authentication method (default: bot_token).",
    )
    group.addoption(
        "--mm-on-failure-only",
        action="store_true",
        default=False,
        help="Only post to Mattermost when the suite has failures.",
    )


class MattermostPlugin:
    """Collects results during the session and posts a summary at the end."""

    def __init__(
        self,
        client: MattermostClient,
        *,
        on_failure_only: bool = False,
        project: str | None = None,
        branch: str | None = None,
        commit: str | None = None,
        run_url: str | None = None,
    ) -> None:
        self._client = client
        self._on_failure_only = on_failure_only
        self._project = project
        self._branch = branch
        self._commit = commit
        self._run_url = run_url

        self._passed = 0
        self._failed = 0
        self._skipped = 0
        self._errors = 0
        self._xfailed = 0
        self._xpassed = 0
        self._failures: list[FailedTest] = []
        self._start_time: float | None = None
        self._end_time: float | None = None

    def pytest_sessionstart(self, session: pytest.Session) -> None:
        self._start_time = time.monotonic()

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item: pytest.Item, call: pytest.CallInfo):  # type: ignore[type-arg, no-untyped-def]
        outcome = yield
        report: pytest.TestReport = outcome.get_result()

        if report.when == "call":
            self._record(report)
        elif report.when in ("setup", "teardown") and report.failed:
            self._record(report, is_error=True)

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        self._end_time = time.monotonic()

        summary = self._build_summary()

        if self._on_failure_only and summary.is_green:
            logger.info("Suite passed - skipping Mattermost notification (--mm-on-failure-only).")
            return

        text, props = render_summary(summary)

        try:
            self._client.post_message(text, props=props)
            logger.info("Mattermost report posted successfully.")
        except MattermostPostError:
            logger.exception("Failed to post Mattermost report.")

    def _record(self, report: pytest.TestReport, *, is_error: bool = False) -> None:
        if is_error:
            self._errors += 1
            self._failures.append(self._build_failed_test(report))
            return

        if report.passed:
            if hasattr(report, "wasxfail"):
                self._xpassed += 1
            else:
                self._passed += 1
        elif report.failed:
            self._failed += 1
            self._failures.append(self._build_failed_test(report))
        elif report.skipped:
            if hasattr(report, "wasxfail"):
                self._xfailed += 1
            else:
                self._skipped += 1

    @staticmethod
    def _build_failed_test(report: pytest.TestReport) -> FailedTest:
        longrepr = report.longrepr
        message = ""
        if hasattr(longrepr, "reprcrash") and longrepr.reprcrash:  # type: ignore[union-attr]
            message = longrepr.reprcrash.message  # type: ignore[union-attr]
        return FailedTest(
            nodeid=report.nodeid,
            message=message,
            traceback=str(longrepr) if longrepr else "",
        )

    def _build_summary(self) -> TestRunSummary:
        duration = 0.0
        if self._start_time is not None and self._end_time is not None:
            duration = self._end_time - self._start_time

        return TestRunSummary(
            passed=self._passed,
            failed=self._failed,
            skipped=self._skipped,
            errors=self._errors,
            xfailed=self._xfailed,
            xpassed=self._xpassed,
            duration_seconds=duration,
            failures=self._failures,
            project=self._project,
            branch=self._branch,
            commit=self._commit,
            run_url=self._run_url,
        )


def pytest_configure(config: pytest.Config) -> None:
    """Instantiate and register the plugin only when explicitly enabled."""
    if not config.getoption("--mattermost", default=False):
        return

    auth_str: str = config.getoption("--mm-auth-method", default="bot_token")
    auth_method = AuthMethod.WEBHOOK if auth_str == "webhook" else AuthMethod.BOT_TOKEN

    try:
        mm_config = MattermostConfig(
            base_url=os.environ.get("MATTERMOST_URL") or None,
            auth_method=auth_method,
            token=os.environ.get("MATTERMOST_TOKEN") or None,
            webhook_url=os.environ.get("MATTERMOST_WEBHOOK_URL") or None,
            channel_id=os.environ.get("MATTERMOST_CHANNEL_ID") or None,
            verify_ssl=os.environ.get("MATTERMOST_VERIFY_SSL", "true").lower() == "true",
        )
        client = MattermostClient(mm_config)
    except ValueError as exc:
        logger.error(f"Mattermost plugin disabled - bad config: {exc}")
        return

    plugin = MattermostPlugin(
        client,
        on_failure_only=config.getoption("--mm-on-failure-only", default=False),
        project=os.environ.get("MATTERMOST_PROJECT"),
        branch=os.environ.get("MATTERMOST_BRANCH"),
        commit=os.environ.get("MATTERMOST_COMMIT"),
        run_url=os.environ.get("MATTERMOST_RUN_URL"),
    )
    config.pluginmanager.register(plugin, name="mattermost-reporter")

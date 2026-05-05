"""Tests for the message attachment rendering."""

from __future__ import annotations

from pytest_mattermost.report import (
    FailedTest,
    TestRunSummary,
    render_summary,
)


def _attachment(summary: TestRunSummary) -> dict:
    _, props = render_summary(summary)
    return props["attachments"][0]


class TestAttachmentShape:
    def test_basic_passed_run(self) -> None:
        att = _attachment(TestRunSummary(passed=10, duration_seconds=1.5))
        assert att["color"] == "#2ecc71"
        assert "PASSED" in att["title"]
        assert att["author_name"] == "pytest-mattermost"
        assert "ts" in att
        # No failures → no text body.
        assert "text" not in att

    def test_failed_run_color_and_failures_block(self) -> None:
        summary = TestRunSummary(
            passed=1,
            failed=2,
            failures=[
                FailedTest(nodeid="test_a", message="boom", traceback="trace-a"),
                FailedTest(nodeid="test_b", message="kaboom", traceback="trace-b"),
            ],
        )
        att = _attachment(summary)
        assert att["color"] == "#e74c3c"
        assert "FAILED" in att["title"]
        assert "test_a" in att["text"]
        assert "test_b" in att["text"]
        assert "trace-a" in att["text"]

    def test_warn_color_when_passed_with_skips(self) -> None:
        att = _attachment(TestRunSummary(passed=5, skipped=2))
        assert att["color"] == "#f1c40f"

    def test_only_nonzero_stats_appear_as_fields(self) -> None:
        summary = TestRunSummary(passed=3, failed=1, skipped=0, errors=0)
        att = _attachment(summary)
        titles = [f["title"] for f in att["fields"]]
        assert any("Passed" in t for t in titles)
        assert any("Failed" in t for t in titles)
        assert not any("Skipped" in t for t in titles)
        assert not any("Errors" in t for t in titles)

    def test_run_url_becomes_title_link(self) -> None:
        att = _attachment(TestRunSummary(passed=1, run_url="https://ci.example.com/123"))
        assert att["title_link"] == "https://ci.example.com/123"

    def test_no_pretext_without_branch_or_commit(self) -> None:
        att = _attachment(TestRunSummary(passed=1))
        assert "pretext" not in att

    def test_pretext_contains_branch_and_commit(self) -> None:
        att = _attachment(TestRunSummary(
            passed=1, branch="main", commit="abcdef1234567890",
        ))
        assert "main" in att["pretext"]
        assert "abcdef12" in att["pretext"]

    def test_footer_contains_project_and_duration(self) -> None:
        att = _attachment(TestRunSummary(
            passed=2, project="my-project", duration_seconds=3.14,
        ))
        assert "my-project" in att["footer"]
        assert "3.14" in att["footer"]

    def test_failures_truncated_with_more_indicator(self) -> None:
        failures = [FailedTest(nodeid=f"test_{i}", message="x") for i in range(8)]
        att = _attachment(TestRunSummary(failed=8, failures=failures))
        assert "more failure" in att["text"]

    def test_traceback_truncation(self) -> None:
        long_trace = "x" * 5000
        failures = [FailedTest(nodeid="test_a", message="m", traceback=long_trace)]
        att = _attachment(TestRunSummary(failed=1, failures=failures))
        assert "…" in att["text"]
        assert len(att["text"]) < 5000

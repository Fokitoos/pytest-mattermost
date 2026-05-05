"""Pytest result message templates for Mattermost.

Produces a rich Mattermost *message attachment* with a colored sidebar,
structured stat fields, an optional clickable title, a footer line, and
a failures block in the body.
See https://developers.mattermost.com/integrate/reference/message-attachments/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar

# Mattermost attachment sidebar colors (hex).
_COLOR_PASS = "#2ecc71"   # green
_COLOR_WARN = "#f1c40f"   # yellow — passed but with skips/warnings
_COLOR_FAIL = "#e74c3c"   # red

# Max characters of a single failure traceback to embed.
_TRACEBACK_LIMIT = 1500
# Max number of failures to include verbatim — extras get a "+N more" line.
_MAX_FAILURES_SHOWN = 5


@dataclass(frozen=True)
class FailedTest:
    """A single failed test entry."""

    nodeid: str
    message: str = ""
    traceback: str = ""


@dataclass(frozen=True)
class TestRunSummary:
    """Aggregated pytest results for one run."""

    __test__: ClassVar[bool] = False  # tell pytest this is not a test class

    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    xfailed: int = 0
    xpassed: int = 0
    duration_seconds: float = 0.0
    failures: list[FailedTest] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    # Optional context — surfaced in the message header / footer.
    project: str | None = None
    branch: str | None = None
    commit: str | None = None
    run_url: str | None = None

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.skipped + self.errors + self.xfailed + self.xpassed

    @property
    def is_green(self) -> bool:
        return self.failed == 0 and self.errors == 0

    @property
    def color(self) -> str:
        if not self.is_green:
            return _COLOR_FAIL
        if self.skipped or self.xfailed:
            return _COLOR_WARN
        return _COLOR_PASS

    @property
    def status_emoji(self) -> str:
        if self.errors:
            return "💥"
        if self.failed:
            return "❌"
        if self.skipped or self.xfailed:
            return "⚠️"
        return "✅"

    @property
    def status_label(self) -> str:
        if self.errors:
            return "ERRORED"
        if self.failed:
            return "FAILED"
        return "PASSED"


def _fmt_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes, secs = divmod(seconds, 60)
    return f"{int(minutes)}m {secs:.1f}s"


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _stat_fields(summary: TestRunSummary) -> list[dict[str, Any]]:
    """Outcome counts (non-zero only) plus any user-supplied metadata fields."""
    candidates = [
        ("✅ Passed", summary.passed),
        ("❌ Failed", summary.failed),
        ("💥 Errors", summary.errors),
        ("⏭️ Skipped", summary.skipped),
        ("🔮 XFailed", summary.xfailed),
        ("🎯 XPassed", summary.xpassed),
    ]
    fields: list[dict[str, Any]] = [
        {"title": label, "value": str(count), "short": True}
        for label, count in candidates
        if count
    ]
    for key, value in summary.metadata.items():
        fields.append({"title": key, "value": value, "short": True})
    return fields


def _context_pretext(summary: TestRunSummary) -> str:
    """Branch/commit subtext shown above the attachment body."""
    bits: list[str] = []
    if summary.branch:
        bits.append(f"🌿 `{summary.branch}`")
    if summary.commit:
        bits.append(f"`{summary.commit[:8]}`")
    return " · ".join(bits)


def _failures_block(failures: list[FailedTest]) -> str:
    if not failures:
        return ""
    shown = failures[:_MAX_FAILURES_SHOWN]
    chunks = ["#### 🔥 Failures"]
    for f in shown:
        chunks.append(f"\n**`{f.nodeid}`**")
        if f.message:
            chunks.append(f"> {f.message.strip().splitlines()[0]}")
        if f.traceback:
            chunks.append("```python\n" + _truncate(f.traceback, _TRACEBACK_LIMIT) + "\n```")
    extra = len(failures) - len(shown)
    if extra > 0:
        chunks.append(f"\n_…and **{extra}** more failure(s) not shown._")
    return "\n".join(chunks)


def _footer(summary: TestRunSummary) -> str:
    bits = ["pytest"]
    if summary.project:
        bits.append(summary.project)
    bits.append(f"⏱ {_fmt_duration(summary.duration_seconds)}")
    bits.append(f"Σ {summary.total}")
    return " · ".join(bits)


def render_summary(summary: TestRunSummary) -> tuple[str, dict[str, Any]]:
    """Render a `TestRunSummary` as ``(text, props)`` for ``post_message``.

    The top-level ``text`` is a short fallback summary; the rich content
    lives in the Mattermost attachment under ``props["attachments"]``.
    """
    fallback = (
        f"{summary.status_emoji} Pytest {summary.status_label} — "
        f"{summary.passed}✅ / {summary.failed}❌ / {summary.skipped}⏭️ "
        f"in {_fmt_duration(summary.duration_seconds)}"
    )

    title = f"{summary.status_emoji} {summary.status_label}"
    if summary.project:
        title = f"{title} — {summary.project}"

    attachment: dict[str, Any] = {
        "fallback": fallback,
        "color": summary.color,
        "author_name": "pytest-mattermost",
        "title": title,
        "fields": _stat_fields(summary),
        "footer": _footer(summary),
        "ts": int(datetime.now(timezone.utc).timestamp()),
        "mrkdwn_in": ["text", "pretext"],
    }

    pretext = _context_pretext(summary)
    if pretext:
        attachment["pretext"] = pretext

    if summary.run_url:
        attachment["title_link"] = summary.run_url

    failures = _failures_block(summary.failures)
    if failures:
        attachment["text"] = failures

    return fallback, {"attachments": [attachment]}

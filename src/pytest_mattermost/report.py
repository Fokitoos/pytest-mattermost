"""Pytest result message templates for Mattermost.

Produces a Markdown body plus a Mattermost *message attachment* with a
colored sidebar, summary fields, and a collapsible failures section.
See https://developers.mattermost.com/integrate/reference/message-attachments/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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

    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    xfailed: int = 0
    xpassed: int = 0
    duration_seconds: float = 0.0
    failures: list[FailedTest] = field(default_factory=list)
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


def _header_line(summary: TestRunSummary) -> str:
    """The big top-line summary the eye lands on first."""
    bits = [f"{summary.status_emoji} **Pytest {summary.status_label}**"]
    if summary.project:
        bits.append(f"`{summary.project}`")
    if summary.branch:
        bits.append(f"on 🌿 `{summary.branch}`")
    if summary.commit:
        bits.append(f"@ `{summary.commit[:8]}`")
    return " ".join(bits)


def _stats_table(summary: TestRunSummary) -> str:
    """A compact emoji + count table rendered as Markdown."""
    rows = [
        ("✅ Passed", summary.passed),
        ("❌ Failed", summary.failed),
        ("💥 Errors", summary.errors),
        ("⏭️ Skipped", summary.skipped),
        ("🔮 XFailed", summary.xfailed),
        ("🎯 XPassed", summary.xpassed),
    ]
    rows = [(label, count) for label, count in rows if count]
    if not rows:
        return "_no tests collected_"

    header = "| " + " | ".join(label for label, _ in rows) + " |"
    sep = "|" + "|".join([":---:"] * len(rows)) + "|"
    body = "| " + " | ".join(str(count) for _, count in rows) + " |"
    return "\n".join([header, sep, body])


def _failures_block(failures: list[FailedTest]) -> str:
    if not failures:
        return ""
    shown = failures[:_MAX_FAILURES_SHOWN]
    chunks = ["", "---", "### 🔥 Failures"]
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


def render_summary(summary: TestRunSummary) -> tuple[str, dict[str, Any]]:
    """Render a `TestRunSummary` as ``(text, props)`` for ``post_message``.

    The ``text`` is a short fallback header; the rich content lives in the
    Mattermost attachment under ``props["attachments"]`` so we get the
    colored sidebar and structured fields.
    """
    fallback = f"{summary.status_emoji} Pytest {summary.status_label} — " \
               f"{summary.passed}✅ / {summary.failed}❌ / {summary.skipped}⏭️ " \
               f"in {_fmt_duration(summary.duration_seconds)}"

    fields: list[dict[str, Any]] = [
        {"title": "Total", "value": str(summary.total), "short": True},
        {"title": "Duration", "value": _fmt_duration(summary.duration_seconds), "short": True},
    ]
    if summary.run_url:
        fields.append({"title": "Run", "value": f"[open ↗]({summary.run_url})", "short": True})

    pretext = _header_line(summary)
    body = _stats_table(summary) + _failures_block(summary.failures)

    attachment = {
        "fallback": fallback,
        "color": summary.color,
        "pretext": pretext,
        "text": body,
        "fields": fields,
        "mrkdwn_in": ["text", "pretext"],
    }
    return fallback, {"attachments": [attachment]}

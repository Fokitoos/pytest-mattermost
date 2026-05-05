"""Tests for the pytest plugin wiring — especially environment-variable flow."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from pytest_mattermost import METADATA_KEY
from pytest_mattermost.client import AuthMethod, MattermostClient
from pytest_mattermost.plugin import MattermostPlugin, pytest_configure


def _make_config_stub(options: dict[str, Any]) -> MagicMock:
    """Build a minimal pytest.Config stub for pytest_configure()."""
    cfg = MagicMock()
    cfg.getoption.side_effect = lambda name, default=None: options.get(name, default)
    cfg.pluginmanager.register = MagicMock()
    return cfg


# -- Env-var → MattermostConfig flow -----------------------------------------


class TestEnvVarConfigFlow:
    def test_bot_token_env_vars_are_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MATTERMOST_URL", "https://mm.example.com")
        monkeypatch.setenv("MATTERMOST_TOKEN", "tok-from-env")
        monkeypatch.setenv("MATTERMOST_CHANNEL_ID", "chan-from-env")

        captured: dict[str, MattermostPlugin] = {}

        def fake_register(plugin: MattermostPlugin, name: str) -> None:
            captured["plugin"] = plugin

        cfg = _make_config_stub({
            "--mattermost": True,
            "--mm-auth-method": "bot_token",
        })
        cfg.pluginmanager.register = fake_register

        pytest_configure(cfg)

        registered = captured["plugin"]
        mm_cfg = registered._client._config
        assert mm_cfg.auth_method is AuthMethod.BOT_TOKEN
        assert mm_cfg.base_url == "https://mm.example.com/"
        assert mm_cfg.token == "tok-from-env"
        assert mm_cfg.channel_id == "chan-from-env"

    def test_webhook_env_var_is_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MATTERMOST_WEBHOOK_URL", "https://mm.example.com/hooks/xyz")

        captured: dict[str, MattermostPlugin] = {}
        cfg = _make_config_stub({
            "--mattermost": True,
            "--mm-auth-method": "webhook",
        })
        cfg.pluginmanager.register = lambda plugin, name: captured.update({"plugin": plugin})

        pytest_configure(cfg)

        mm_cfg = captured["plugin"]._client._config
        assert mm_cfg.auth_method is AuthMethod.WEBHOOK
        assert mm_cfg.webhook_url == "https://mm.example.com/hooks/xyz"

    def test_verify_ssl_env_var_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MATTERMOST_WEBHOOK_URL", "https://mm.example.com/hooks/xyz")
        monkeypatch.setenv("MATTERMOST_VERIFY_SSL", "false")

        captured: dict[str, MattermostPlugin] = {}
        cfg = _make_config_stub({"--mattermost": True, "--mm-auth-method": "webhook"})
        cfg.pluginmanager.register = lambda plugin, name: captured.update({"plugin": plugin})

        pytest_configure(cfg)

        assert captured["plugin"]._client._config.verify_ssl is False

    def test_verify_ssl_env_var_default_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MATTERMOST_WEBHOOK_URL", "https://mm.example.com/hooks/xyz")

        captured: dict[str, MattermostPlugin] = {}
        cfg = _make_config_stub({"--mattermost": True, "--mm-auth-method": "webhook"})
        cfg.pluginmanager.register = lambda plugin, name: captured.update({"plugin": plugin})

        pytest_configure(cfg)

        assert captured["plugin"]._client._config.verify_ssl is True

    @pytest.mark.parametrize(
        "env_name,attr",
        [
            ("MATTERMOST_PROJECT", "_project"),
            ("MATTERMOST_BRANCH", "_branch"),
            ("MATTERMOST_COMMIT", "_commit"),
            ("MATTERMOST_RUN_URL", "_run_url"),
        ],
    )
    def test_optional_context_env_vars(
        self, monkeypatch: pytest.MonkeyPatch, env_name: str, attr: str,
    ) -> None:
        monkeypatch.setenv("MATTERMOST_WEBHOOK_URL", "https://mm.example.com/hooks/xyz")
        monkeypatch.setenv(env_name, "value-for-" + env_name)

        captured: dict[str, MattermostPlugin] = {}
        cfg = _make_config_stub({"--mattermost": True, "--mm-auth-method": "webhook"})
        cfg.pluginmanager.register = lambda plugin, name: captured.update({"plugin": plugin})

        pytest_configure(cfg)

        assert getattr(captured["plugin"], attr) == "value-for-" + env_name

    def test_optional_context_env_vars_default_to_none(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("MATTERMOST_WEBHOOK_URL", "https://mm.example.com/hooks/xyz")

        captured: dict[str, MattermostPlugin] = {}
        cfg = _make_config_stub({"--mattermost": True, "--mm-auth-method": "webhook"})
        cfg.pluginmanager.register = lambda plugin, name: captured.update({"plugin": plugin})

        pytest_configure(cfg)

        plugin = captured["plugin"]
        assert plugin._project is None
        assert plugin._branch is None
        assert plugin._commit is None
        assert plugin._run_url is None


# -- pytest_configure guard rails --------------------------------------------


class TestPytestConfigureGuards:
    def test_disabled_when_flag_not_passed(self) -> None:
        cfg = _make_config_stub({"--mattermost": False})
        pytest_configure(cfg)
        cfg.pluginmanager.register.assert_not_called()

    def test_disabled_on_bad_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # No env vars set — webhook auth will fail validation.
        cfg = _make_config_stub({"--mattermost": True, "--mm-auth-method": "webhook"})
        pytest_configure(cfg)
        cfg.pluginmanager.register.assert_not_called()

    def test_disabled_on_invalid_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MATTERMOST_WEBHOOK_URL", "not-a-url")
        cfg = _make_config_stub({"--mattermost": True, "--mm-auth-method": "webhook"})
        pytest_configure(cfg)
        cfg.pluginmanager.register.assert_not_called()


# -- End-to-end: optional context env vars reach the rendered summary --------


class TestRunUrlReachesSummary:
    """Verify MATTERMOST_RUN_URL (and friends) actually flow into the posted payload."""

    def test_run_url_appears_in_posted_props(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("MATTERMOST_WEBHOOK_URL", "https://mm.example.com/hooks/xyz")
        monkeypatch.setenv("MATTERMOST_PROJECT", "my-project")
        monkeypatch.setenv("MATTERMOST_BRANCH", "main")
        monkeypatch.setenv("MATTERMOST_COMMIT", "abcdef1234567890")
        monkeypatch.setenv("MATTERMOST_RUN_URL", "https://ci.example.com/run/42")

        captured: dict[str, MattermostPlugin] = {}
        cfg = _make_config_stub({"--mattermost": True, "--mm-auth-method": "webhook"})
        cfg.pluginmanager.register = lambda plugin, name: captured.update({"plugin": plugin})

        pytest_configure(cfg)

        plugin = captured["plugin"]
        # Capture the post call instead of letting it hit the network.
        sent: dict[str, Any] = {}
        plugin._client.post_message = lambda text, *, props=None: sent.update(  # type: ignore[method-assign]
            {"text": text, "props": props}
        ) or {"status": "ok"}

        # Drive the lifecycle.
        plugin.pytest_sessionstart(session=MagicMock())
        plugin.pytest_sessionfinish(session=MagicMock(), exitstatus=0)

        attachment = sent["props"]["attachments"][0]
        assert "my-project" in attachment["title"]
        assert "main" in attachment["pretext"]
        assert "abcdef12" in attachment["pretext"]  # truncated to first 8
        assert attachment["title_link"] == "https://ci.example.com/run/42"
        assert "my-project" in attachment["footer"]


# -- Outcome recording --------------------------------------------------------


class TestOutcomeRecording:
    def _make_plugin(self) -> MattermostPlugin:
        client = MagicMock(spec=MattermostClient)
        return MattermostPlugin(client)

    def test_passed_increments_passed(self) -> None:
        plugin = self._make_plugin()
        report = MagicMock(passed=True, failed=False, skipped=False)
        del report.wasxfail  # ensure hasattr() returns False
        plugin._record(report)
        assert plugin._passed == 1

    def test_failed_records_failure(self) -> None:
        plugin = self._make_plugin()
        report = MagicMock(passed=False, failed=True, skipped=False, nodeid="test_a")
        report.longrepr = "traceback text"
        plugin._record(report)
        assert plugin._failed == 1
        assert plugin._failures[0].nodeid == "test_a"

    def test_setup_error_counts_as_error(self) -> None:
        plugin = self._make_plugin()
        report = MagicMock(passed=False, failed=True, skipped=False, nodeid="test_b")
        report.longrepr = "error"
        plugin._record(report, is_error=True)
        assert plugin._errors == 1
        assert plugin._failures[0].nodeid == "test_b"

    def test_on_failure_only_skips_post_when_green(self) -> None:
        client = MagicMock(spec=MattermostClient)
        plugin = MattermostPlugin(client, on_failure_only=True)
        plugin.pytest_sessionstart(session=MagicMock())
        plugin.pytest_sessionfinish(session=MagicMock(), exitstatus=0)
        client.post_message.assert_not_called()

    def test_on_failure_only_posts_when_failed(self) -> None:
        client = MagicMock(spec=MattermostClient)
        plugin = MattermostPlugin(client, on_failure_only=True)
        plugin.pytest_sessionstart(session=MagicMock())
        report = MagicMock(passed=False, failed=True, skipped=False, nodeid="test_x")
        report.longrepr = "boom"
        plugin._record(report)
        plugin.pytest_sessionfinish(session=MagicMock(), exitstatus=1)
        client.post_message.assert_called_once()


# -- Metadata stash ----------------------------------------------------------


class TestMetadataStash:
    def test_metadata_from_stash_appears_in_attachment(self) -> None:
        client = MagicMock(spec=MattermostClient)
        plugin = MattermostPlugin(client)
        plugin.pytest_sessionstart(session=MagicMock())

        session = MagicMock()
        session.config.stash.get.return_value = {
            "Environment": "staging",
            "Python": "3.12.0",
        }
        sent: dict = {}
        client.post_message.side_effect = lambda text, *, props=None: sent.update(
            {"text": text, "props": props}
        )

        plugin.pytest_sessionfinish(session=session, exitstatus=0)

        fields = sent["props"]["attachments"][0]["fields"]
        field_map = {f["title"]: f["value"] for f in fields}
        assert field_map["Environment"] == "staging"
        assert field_map["Python"] == "3.12.0"

    def test_empty_stash_produces_no_extra_fields(self) -> None:
        client = MagicMock(spec=MattermostClient)
        plugin = MattermostPlugin(client)
        plugin._passed = 5
        plugin.pytest_sessionstart(session=MagicMock())

        session = MagicMock()
        session.config.stash.get.return_value = {}
        sent: dict = {}
        client.post_message.side_effect = lambda text, *, props=None: sent.update(
            {"text": text, "props": props}
        )

        plugin.pytest_sessionfinish(session=session, exitstatus=0)

        fields = sent["props"]["attachments"][0]["fields"]
        assert all(f["title"] in {"✅ Passed", "❌ Failed", "💥 Errors", "⏭️ Skipped", "🔮 XFailed", "🎯 XPassed"} for f in fields)

"""Tests for MattermostConfig and MattermostClient."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from pytest_mattermost.client import (
    AuthMethod,
    MattermostClient,
    MattermostConfig,
    MattermostPostError,
)


# -- MattermostConfig validation ---------------------------------------------


class TestMattermostConfigValidation:
    def test_bot_token_requires_base_url(self) -> None:
        with pytest.raises(ValidationError, match="base_url is required"):
            MattermostConfig(
                auth_method=AuthMethod.BOT_TOKEN,
                token="t",
                channel_id="c",
            )

    def test_bot_token_requires_token(self) -> None:
        with pytest.raises(ValidationError, match="token is required"):
            MattermostConfig(
                auth_method=AuthMethod.BOT_TOKEN,
                base_url="https://mm.example.com",
                channel_id="c",
            )

    def test_bot_token_requires_channel_id(self) -> None:
        with pytest.raises(ValidationError, match="channel_id is required"):
            MattermostConfig(
                auth_method=AuthMethod.BOT_TOKEN,
                base_url="https://mm.example.com",
                token="t",
            )

    def test_webhook_requires_webhook_url(self) -> None:
        with pytest.raises(ValidationError, match="webhook_url is required"):
            MattermostConfig(auth_method=AuthMethod.WEBHOOK)

    def test_bot_token_valid_config(self) -> None:
        cfg = MattermostConfig(
            auth_method=AuthMethod.BOT_TOKEN,
            base_url="https://mm.example.com",
            token="my-token",
            channel_id="abc123",
        )
        assert cfg.base_url == "https://mm.example.com/"
        assert cfg.token == "my-token"
        assert cfg.channel_id == "abc123"

    def test_webhook_valid_config(self) -> None:
        cfg = MattermostConfig(
            auth_method=AuthMethod.WEBHOOK,
            webhook_url="https://mm.example.com/hooks/xyz",
        )
        assert cfg.webhook_url == "https://mm.example.com/hooks/xyz"

    def test_invalid_url_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MattermostConfig(
                auth_method=AuthMethod.WEBHOOK,
                webhook_url="not-a-url",
            )

    def test_url_stored_as_str(self) -> None:
        cfg = MattermostConfig(
            auth_method=AuthMethod.WEBHOOK,
            webhook_url="https://mm.example.com/hooks/xyz",
        )
        assert isinstance(cfg.webhook_url, str)

    def test_config_is_frozen(self) -> None:
        cfg = MattermostConfig(
            auth_method=AuthMethod.WEBHOOK,
            webhook_url="https://mm.example.com/hooks/xyz",
        )
        with pytest.raises(ValidationError):
            cfg.token = "new-token"  # type: ignore[misc]

    def test_defaults(self) -> None:
        cfg = MattermostConfig(
            auth_method=AuthMethod.WEBHOOK,
            webhook_url="https://mm.example.com/hooks/xyz",
        )
        assert cfg.timeout == 30
        assert cfg.max_retries == 3
        assert cfg.verify_ssl is True


# -- MattermostClient HTTP behavior ------------------------------------------


def _make_response(status_code: int = 200, json_data: dict[str, Any] | None = None,
                   content_type: str = "application/json") -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.headers = {"Content-Type": content_type}
    response.json.return_value = json_data or {}
    response.raise_for_status.return_value = None
    return response


class TestMattermostClient:
    def test_post_via_webhook(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = MattermostConfig(
            auth_method=AuthMethod.WEBHOOK,
            webhook_url="https://mm.example.com/hooks/xyz",
        )
        client = MattermostClient(cfg)

        captured: dict[str, Any] = {}

        def fake_post(url: str, json: dict[str, Any], timeout: int) -> MagicMock:
            captured["url"] = url
            captured["json"] = json
            return _make_response(content_type="text/plain")

        monkeypatch.setattr(client._session, "post", fake_post)

        result = client.post_message("hello")

        assert captured["url"] == "https://mm.example.com/hooks/xyz"
        assert captured["json"] == {"text": "hello"}
        assert result == {"status": "ok"}

    def test_post_via_bot_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = MattermostConfig(
            auth_method=AuthMethod.BOT_TOKEN,
            base_url="https://mm.example.com",
            token="my-token",
            channel_id="abc123",
        )
        client = MattermostClient(cfg)

        captured: dict[str, Any] = {}

        def fake_post(url: str, json: dict[str, Any], timeout: int) -> MagicMock:
            captured["url"] = url
            captured["json"] = json
            return _make_response(json_data={"id": "post-1"})

        monkeypatch.setattr(client._session, "post", fake_post)

        result = client.post_message("hello", props={"attachments": []})

        assert captured["url"] == "https://mm.example.com/api/v4/posts"
        assert captured["json"] == {
            "channel_id": "abc123",
            "message": "hello",
            "props": {"attachments": []},
        }
        assert result == {"id": "post-1"}
        assert client._session.headers["Authorization"] == "Bearer my-token"

    def test_post_failure_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import requests

        cfg = MattermostConfig(
            auth_method=AuthMethod.WEBHOOK,
            webhook_url="https://mm.example.com/hooks/xyz",
        )
        client = MattermostClient(cfg)

        def fake_post(*args: Any, **kwargs: Any) -> MagicMock:
            raise requests.ConnectionError("boom")

        monkeypatch.setattr(client._session, "post", fake_post)

        with pytest.raises(MattermostPostError, match="Failed to post"):
            client.post_message("hello")

    def test_verify_ssl_propagates_to_session(self) -> None:
        cfg = MattermostConfig(
            auth_method=AuthMethod.WEBHOOK,
            webhook_url="https://mm.example.com/hooks/xyz",
            verify_ssl=False,
        )
        client = MattermostClient(cfg)
        assert client._session.verify is False

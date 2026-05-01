"""Low-level Mattermost HTTP client.

Handles authentication, retries, and the two supported posting
mechanisms (Bot token and Incoming Webhook).
"""

import time
from enum import Enum, auto
from typing import Annotated, Any

import requests
from loguru import logger
from pydantic import AfterValidator, BaseModel, HttpUrl, model_validator
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class AuthMethod(Enum):
    """Supported Mattermost authentication methods."""

    BOT_TOKEN = auto()
    WEBHOOK = auto()


class MattermostConfig(BaseModel):
    """Immutable configuration for the Mattermost connection.

    Attributes:
        base_url:    Mattermost server URL, e.g. ``https://mm.example.com``.
        auth_method: How to authenticate bot token or incoming webhook.
        token:       Bot / personal-access token (required for BOT_TOKEN).
        webhook_url: Full incoming-webhook URL (required for WEBHOOK).
        channel_id:  Target channel ID (required for BOT_TOKEN).
        timeout:     HTTP timeout in seconds.
        max_retries: Number of retry attempts on transient failures.
        verify_ssl:  Whether to verify TLS certificates.
    """
    model_config = {"frozen": True}

    base_url: Annotated[str, AfterValidator(lambda v: str(HttpUrl(v)))] | None = ""
    auth_method: AuthMethod = AuthMethod.WEBHOOK
    token: str | None = None
    webhook_url: Annotated[str, AfterValidator(lambda v: str(HttpUrl(v)))] | None = ""
    channel_id: str | None = None
    timeout: int = 30
    max_retries: int = 3
    verify_ssl: bool = True

    @model_validator(mode="after")
    def _check_required_fields(self) -> "MattermostConfig":
        if self.auth_method is AuthMethod.BOT_TOKEN:
            if not self.base_url:
                raise ValueError("base_url is required for BOT_TOKEN auth")
            if not self.token:
                raise ValueError("token is required for BOT_TOKEN auth")
            if not self.channel_id:
                raise ValueError("channel_id is required for BOT_TOKEN auth")
        elif self.auth_method is AuthMethod.WEBHOOK:
            if not self.webhook_url:
                raise ValueError("webhook_url is required for WEBHOOK auth")
        return self


class MattermostClient:
    """Wrapper around the Mattermost REST API.

    Usage:

        cfg = MattermostConfig(
            base_url="https://mm.example.com",
            token="my-bot-token",
            channel_id="somechannelid123",
        )
        # or with a webhook
        # cfg = MattermostConfig(
        #   webhook_url="my_webhook_url",
        #   )
        client = MattermostClient(cfg)
        client.post_message("Hello from Pytest!")
    """

    def __init__(self, config: MattermostConfig) -> None:
        self._config = config
        self._session = self._build_session()

    def post_message(self, text: str, *, props: dict[str, Any] | None = None) -> dict[str, Any]:
        """Publish a message to the configured channel.

        Args:
            text:  Markdown-formatted message body.
            props: Optional extra props (attachments, etc.).

        Returns:
            The JSON response from Mattermost.

        Raises:
            MattermostPostError: When the message could not be delivered
                after all retries.
        """
        if self._config.auth_method is AuthMethod.WEBHOOK:
            return self._post_via_webhook(text, props)
        return self._post_via_api(text, props)

    def _build_session(self) -> requests.Session:
        """Create a ``requests.Session`` with retry / back-off."""
        session = requests.Session()
        retry_strategy = Retry(
            total=self._config.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        if self._config.auth_method is AuthMethod.BOT_TOKEN:
            session.headers.update({
                "Authorization": f"Bearer {self._config.token}",
                "Content-Type": "application/json",
            })

        session.verify = self._config.verify_ssl
        return session

    def _post_via_api(self, text: str, props: dict[str, Any] | None) -> dict[str, Any]:
        """Post using the ``/api/v4/posts`` endpoint (bot token)."""
        url = f"{self._config.base_url.rstrip('/')}/api/v4/posts"
        payload: dict[str, Any] = {
            "channel_id": self._config.channel_id,
            "message": text,
        }
        if props:
            payload["props"] = props

        return self._send(url, payload)

    def _post_via_webhook(self, text: str, props: dict[str, Any] | None) -> dict[str, Any]:
        """Post using an incoming webhook URL."""
        payload: dict[str, Any] = {"text": text}
        if props:
            payload["props"] = props

        return self._send(self._config.webhook_url, payload)

    def _send(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Fire the HTTP request and handle errors uniformly."""
        start = time.monotonic()
        try:
            response = self._session.post(url, json=payload, timeout=self._config.timeout)
            elapsed = time.monotonic() - start
            logger.debug("POST %s completed in %.2fs (status %d)", url, elapsed, response.status_code)
            response.raise_for_status()
            # Webhooks return "ok" as plain text.
            if response.headers.get("Content-Type", "").startswith("application/json"):
                return response.json()  # type: ignore[no-any-return]
            return {"status": "ok"}
        except requests.RequestException as exc:
            raise MattermostPostError(f"Failed to post to {url}: {exc}") from exc


class MattermostPostError(Exception):
    """Raised when a message could not be delivered to Mattermost."""

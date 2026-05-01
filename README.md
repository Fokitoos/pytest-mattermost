# pytest-mattermost

A pytest plugin that posts a rich test run summary to a Mattermost channel when your suite finishes — with pass/fail counts, a colored sidebar, and the first few failure tracebacks.

## Installation

### From PyPI

```bash
pip install pytest-mattermost
```

Or with `uv`:

```bash
uv add pytest-mattermost
```

### From GitHub directly

Install the latest commit on `main`:

```bash
pip install git+https://github.com/fokitoo/pytest-mattermost.git
```

Pin to a tag, branch, or commit:

```bash
pip install git+https://github.com/fokitoo/pytest-mattermost.git@v0.1.0
pip install git+https://github.com/fokitoo/pytest-mattermost.git@main
pip install git+https://github.com/fokitoo/pytest-mattermost.git@<commit-sha>
```

With `uv`:

```bash
uv add "pytest-mattermost @ git+https://github.com/fokitoo/pytest-mattermost.git"
```

## Usage

The plugin is registered with pytest automatically once installed but stays silent until you pass `--mattermost`. Configure credentials via environment variables.

### Bot token (recommended)

```bash
export MATTERMOST_URL="https://mattermost.example.com"
export MATTERMOST_TOKEN="your-bot-token"
export MATTERMOST_CHANNEL_ID="abc123channelid"

pytest --mattermost
```

### Incoming webhook

```bash
export MATTERMOST_WEBHOOK_URL="https://mattermost.example.com/hooks/xxxxx"

pytest --mattermost --mm-auth-method=webhook
```

## CLI flags

| Flag | Default | Description |
| --- | --- | --- |
| `--mattermost` | `false` | Enable Mattermost reporting. |
| `--mm-auth-method` | `bot_token` | Either `bot_token` or `webhook`. |
| `--mm-on-failure-only` | `false` | Only post when the suite has failures. |

## Environment variables

| Variable | Used by | Description |
| --- | --- | --- |
| `MATTERMOST_URL` | `bot_token` | Base URL of your Mattermost server. |
| `MATTERMOST_TOKEN` | `bot_token` | Bot or personal-access token. |
| `MATTERMOST_CHANNEL_ID` | `bot_token` | ID of the channel to post in. |
| `MATTERMOST_WEBHOOK_URL` | `webhook` | Full incoming-webhook URL. |
| `MATTERMOST_VERIFY_SSL` | both | `false` to skip TLS verification (default `true`). |
| `MATTERMOST_PROJECT` | optional | Project name shown in the report header. |
| `MATTERMOST_BRANCH` | optional | Branch name shown in the report header. |
| `MATTERMOST_COMMIT` | optional | Commit SHA shown in the report header. |
| `MATTERMOST_RUN_URL` | optional | Link to the CI run, added as a field. |

## License

MIT — see [LICENSE](LICENSE).
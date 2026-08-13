# setup-codex

Configure the [OpenAI Codex CLI](https://developers.openai.com/codex) to use models served by [CoreInfra AI Hub](https://hub.coreinfra.ai).

## Prerequisites

You need the Codex CLI, a [CoreInfra AI Hub](https://hub.coreinfra.ai) token, and either `uvx` or `pipx`.

On a new Mac, install Apple's Command Line Tools first. Skip this step if they are already installed.

```sh
xcode-select --install
```

If you do not have `uvx`, [install uv](https://docs.astral.sh/uv/getting-started/installation/):

```sh
brew install uv
```

You can also use uv's official installer or choose the `pipx` command below.

## Quick start

Run setup with your CoreInfra token:

```sh
uvx --from git+https://github.com/CoreInfraAI/setup-codex setup-codex --api-key <your-token>
```

Then verify that Codex works:

```sh
codex exec "2 + 2" --skip-git-repo-check
```

To run setup with `pipx` instead:

```sh
pipx run --spec git+https://github.com/CoreInfraAI/setup-codex setup-codex --api-key <your-token>
```

## What it does

1. Creates a model catalog at `<codex-home>/models.json` from the models available through CoreInfra AI Hub.
2. Configures `<codex-home>/config.toml` to use the `coreinfra` provider while preserving your other settings.
3. Stores your API token in `<codex-home>/.env` with file mode `600` when you pass `--api-key`.
4. Backs up each existing file before changing it. Backups are saved beside the original file with a `.bak` suffix.

## Configuration

### Options

```
--codex-home PATH   codex home directory (default: $CODEX_HOME or ~/.codex)
--model SLUG        default model for a fresh config (default: gpt-5.6-sol)
--api-key TOKEN     CoreInfra API token to write into .env
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `COREINFRA_HUB_BASE_URL` | `https://hub.coreinfra.ai` | Hub endpoint used by setup and written to the Codex config. Override it for another instance, such as staging. Trailing slashes are removed. |

## After a Codex upgrade

Re-run setup after upgrading Codex so the model catalog matches the new binary. Add `--refresh` to bypass the `uvx` cache:

```sh
uvx --refresh --from git+https://github.com/CoreInfraAI/setup-codex setup-codex
```

## Limitations

- Only models served over the **Responses API** are included. Models limited to chat-completions or messages — including Kimi, GLM, Claude — cannot be used by Codex.
- ChatGPT Work currently supports only OpenAI models.

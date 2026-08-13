# setup-codex

One-line setup for using [OpenAI Codex](https://developers.openai.com/codex) CLI with [CoreInfra AI Hub](https://hub.coreinfra.ai).

## Quick start

```sh
uvx --from git+https://github.com/CoreInfraAI/setup-codex setup-codex --api-key <your-token>
```

Get a token at https://hub.coreinfra.ai. Then verify:

```sh
codex exec "2 + 2" --skip-git-repo-check
```

No `uvx`? Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first, e.g. `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`. Alternatively, `pipx run` works the same way:

```sh
pipx run --spec git+https://github.com/CoreInfraAI/setup-codex setup-codex --api-key <your-token>
```

## What it does

1. **Regenerates `<codex-home>/models.json`** — a codex model catalog covering every model CoreInfra AI Hub serves over the Responses API. The model list is fetched live from the hub's [prices endpoint](https://hub.coreinfra.ai/hub/api/prices) (every model with `responses` in its `protocols`). Codex's `model_catalog_json` *replaces* its bundled catalog rather than merging, so the file is rebuilt from your installed codex binary's own bundled catalog (`codex debug models --bundled`) — instruction templates, context windows, and reasoning levels always match your codex version. Models codex doesn't bundle yet get an entry cloned from the closest bundled sibling.
2. **Updates `<codex-home>/config.toml`** — adds the `coreinfra` model provider, `model_catalog_json`, and (on a fresh config) sensible defaults. Existing settings (MCP servers, project trust, other providers) are preserved; already-present keys are only updated where needed.
3. **Optionally writes the API token** to `<codex-home>/.env` (`--api-key`), chmod 600.

## Options

```
--codex-home PATH   codex home directory (default: $CODEX_HOME or ~/.codex)
--model SLUG        default model for a fresh config (default: gpt-5.6-sol)
--api-key TOKEN     CoreInfra API token to write into .env
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `COREINFRA_HUB_BASE_URL` | `https://hub.coreinfra.ai` | Base URL of the CoreInfra Hub instance. Override to point setup-codex — and the codex config it writes — at a different endpoint, e.g. a staging instance for testing. Trailing slashes are stripped. |

## After a codex upgrade

Re-run the same command to refresh the catalog against the new binary (add `--refresh` to bypass the uvx cache):

```sh
uvx --refresh --from git+https://github.com/CoreInfraAI/setup-codex setup-codex
```

## Notes

- Only models the hub serves over the **Responses API** are included; chat-completions and messages models (Kimi, GLM, Claude, `deepseek-v4-pro`) can't be used by codex.
- ChatGPT Work only works with OpenAI models for now

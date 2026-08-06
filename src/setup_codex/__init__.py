"""Configure OpenAI Codex CLI to use CoreInfra AI Hub.

One-liner (no install needed):

    uvx --from git+https://github.com/CoreInfraAI/setup-codex setup-codex

What it does:
  1. Regenerates `models.json` — a codex model catalog covering every model
     CoreInfra AI Hub serves over the Responses API. Codex's
     `model_catalog_json` REPLACES the bundled catalog (no merge), so the file
     is rebuilt from the installed codex binary's own bundled catalog
     (`codex debug models --bundled`) plus CoreInfra-specific entries.
  2. Ensures `config.toml` points at CoreInfra AI Hub (adds only what is
     missing; existing settings are preserved).
  3. Optionally writes your API token to `.env` (--api-key).

Re-run after every codex upgrade to refresh the catalog.
"""

import argparse
import copy
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

PROVIDER_ID = "coreinfra"
PROVIDER_BLOCK = f"""\
[model_providers.{PROVIDER_ID}]
name = "CoreInfra AI Hub"
base_url = "https://hub.coreinfra.ai/openai/api/v1"
wire_api = "responses"
env_key = "COREINFRA_API_KEY"
"""

DEFAULT_MODEL = "gpt-5.6-sol"
PRICES_URL = "https://hub.coreinfra.ai/hub/api/prices"

INTERNAL_MODELS = ["codex-auto-review"]  # hidden; used by approvals_reviewer = "auto_review"


def eprint(*args):
    print(*args, file=sys.stderr)


def bundled_catalog():
    out = subprocess.run(
        ["codex", "debug", "models", "--bundled"],
        check=True, capture_output=True, text=True,
    )
    return {m["slug"]: m for m in json.loads(out.stdout)["models"]}


def hub_models():
    """{slug: display_name} for every model the hub serves over the Responses API.

    Source of truth: the hub's prices endpoint (`protocols` per model).
    """
    try:
        with urllib.request.urlopen(PRICES_URL, timeout=30) as resp:
            data = json.load(resp)
    except Exception as err:
        raise SystemExit(f"error: failed to fetch {PRICES_URL}: {err}")
    models = {}
    for provider in data["providers"].values():
        for slug, info in provider["models"].items():
            if "responses" in info.get("protocols", []):
                models[slug] = info.get("display_name") or slug
    return models


def pick_template(slug, bundled):
    """Best bundled sibling for a slug codex doesn't bundle: same family
    (text before the first '-'), longest common prefix, bundled order wins ties."""
    family = slug.split("-")[0]
    best = None
    for bundled_slug in bundled:
        if bundled_slug.split("-")[0] != family:
            continue
        n = len(os.path.commonprefix([slug, bundled_slug]))
        if best is None or n > best[0]:
            best = (n, bundled_slug)
    return best[1] if best else None


def deepseek_entry(slug):
    """Catalog entry for a DeepSeek model, from the snapshot bundled with
    this package (extracted from DeepSeek's codex setup script)."""
    with open(Path(__file__).with_name("deepseek_models.json")) as f:
        for m in json.load(f)["models"]:
            if m["slug"] == slug:
                return m
    return None


def build_catalog(models_path):
    bundled = bundled_catalog()
    hub = hub_models()
    models = []
    warnings = []

    # Bundled models first, in codex's own order; unbundled hub models after,
    # newest slug first.
    ordered = [s for s in bundled if s in hub]
    ordered += sorted((s for s in hub if s not in bundled), reverse=True)

    for slug in ordered:
        if slug in bundled:
            entry = copy.deepcopy(bundled[slug])
        elif slug.startswith("deepseek"):
            entry = deepseek_entry(slug)
            if entry is None:
                warnings.append(f"skipped {slug}: no bundled catalog entry in deepseek_models.json")
                continue
            entry["description"] = f"{entry['display_name']} served via CoreInfra AI Hub."
            entry["priority"] = len(models) + 1
            models.append(entry)
            continue
        else:
            template = pick_template(slug, bundled)
            if not template:
                warnings.append(f"skipped {slug}: no bundled entry and no suitable template")
                continue
            entry = copy.deepcopy(bundled[template])
            entry["slug"] = slug
            entry["display_name"] = hub[slug]
            entry["description"] = f"{entry['display_name']} served via CoreInfra AI Hub."
        # The hub still serves older models: surface them and mute migration nags.
        entry["visibility"] = "list"
        entry["upgrade"] = None
        entry["availability_nux"] = None
        entry["priority"] = len(models) + 1
        models.append(entry)

    for slug in INTERNAL_MODELS:
        if slug in bundled:
            entry = copy.deepcopy(bundled[slug])
            entry["priority"] = len(models) + 1
            models.append(entry)
        else:
            warnings.append(f"skipped {slug}: missing from bundled catalog")

    return {"models": models}, warnings


def catalog_config_value(codex_home):
    """Tilde-shortened path to models.json for use in config.toml."""
    try:
        rel = codex_home.relative_to(Path.home())
        return str(Path("~") / rel / "models.json")
    except ValueError:
        return str(codex_home / "models.json")


def ensure_config(codex_home, model):
    """Add CoreInfra provider settings to config.toml; preserve everything else."""
    cfg = codex_home / "config.toml"
    catalog_value = catalog_config_value(codex_home)
    if not cfg.exists():
        cfg.write_text(
            f'model_provider = "{PROVIDER_ID}"\n'
            f'model = "{model}"\n'
            f'model_reasoning_effort = "medium"\n'
            f'preferred_auth_method = "apikey"\n'
            f'model_catalog_json = "{catalog_value}"\n'
            f"\n{PROVIDER_BLOCK}"
        )
        return ["created config.toml"]

    text = cfg.read_text()
    changes = []
    m = re.search(r"^\[", text, re.M)
    header, rest = (text[: m.start()], text[m.start():]) if m else (text, "")

    def set_header_key(header, key, value):
        pattern = rf"^{re.escape(key)}\s*=.*$"
        line = f'{key} = "{value}"'
        if re.search(pattern, header, re.M):
            new = re.sub(pattern, line, header, flags=re.M)
            return new, new != header
        sep = "" if header.endswith("\n") or not header else "\n"
        return f"{header}{sep}{line}\n", True

    header, changed = set_header_key(header, "model_catalog_json", catalog_value)
    if changed:
        changes.append("set model_catalog_json")
    for key, value in (("model_provider", PROVIDER_ID), ("model", model)):
        if not re.search(rf"^{re.escape(key)}\s*=", header, re.M):
            sep = "" if header.endswith("\n") or not header else "\n"
            header = f'{header}{sep}{key} = "{value}"\n'
            changes.append(f"added {key}")

    if f"[model_providers.{PROVIDER_ID}]" not in rest:
        rest = rest.rstrip() + "\n\n" + PROVIDER_BLOCK if rest.strip() else PROVIDER_BLOCK
        changes.append("added [model_providers.coreinfra] section")

    if changes:
        cfg.write_text(header + rest)
    return changes or ["config.toml already up to date"]


def ensure_env(codex_home, api_key):
    env_path = codex_home / ".env"
    if api_key:
        existing = env_path.read_text() if env_path.exists() else ""
        line = f"COREINFRA_API_KEY={api_key}"
        if re.search(r"^COREINFRA_API_KEY=", existing, re.M):
            new = re.sub(r"^COREINFRA_API_KEY=.*$", line, existing, flags=re.M)
        else:
            sep = "" if existing.endswith("\n") or not existing else "\n"
            new = f"{existing}{sep}{line}\n"
        env_path.write_text(new)
        env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        return "wrote COREINFRA_API_KEY to .env"
    if not env_path.exists() or "COREINFRA_API_KEY" not in env_path.read_text():
        return (
            "no API token configured — get one at https://hub.coreinfra.ai and either\n"
            "  re-run with --api-key <token>, or add it yourself:\n"
            f"  echo 'COREINFRA_API_KEY=<token>' >> {env_path}"
        )
    return ".env already has COREINFRA_API_KEY"


def validate_toml(codex_home):
    try:
        import tomllib
    except ImportError:
        return
    try:
        with open(codex_home / "config.toml", "rb") as f:
            tomllib.load(f)
    except Exception as err:
        eprint(f"warning: config.toml failed to parse after edit: {err}")


def main():
    parser = argparse.ArgumentParser(
        prog="setup-codex",
        description="Configure OpenAI Codex CLI to use CoreInfra AI Hub.",
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser(),
        help="codex home directory (default: $CODEX_HOME or ~/.codex)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"default model for a fresh config (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--api-key",
        help="CoreInfra API token to write into <codex-home>/.env",
    )
    args = parser.parse_args()

    if not shutil.which("codex"):
        raise SystemExit(
            "error: codex CLI not found on PATH. Install it first:\n"
            "  npm install -g @openai/codex"
        )

    codex_home = args.codex_home
    codex_home.mkdir(parents=True, exist_ok=True)
    models_path = codex_home / "models.json"

    catalog, warnings = build_catalog(models_path)
    fd, tmp = tempfile.mkstemp(dir=codex_home, prefix="models.json.", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(catalog, f, indent=2)
    os.replace(tmp, models_path)
    print(f"wrote {models_path}: {len(catalog['models'])} models")
    for m in catalog["models"]:
        print(f"  {m['slug']:24} {m['display_name']}")
    for w in warnings:
        eprint(f"warning: {w}")

    for change in ensure_config(codex_home, args.model):
        print(f"config.toml: {change}")
    validate_toml(codex_home)
    print(ensure_env(codex_home, args.api_key))

    print("\nDone. Verify with:")
    print('  codex exec "2 + 2" --skip-git-repo-check')


if __name__ == "__main__":
    main()

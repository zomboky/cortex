# cortex

Turns a folder of files into a curated, richly-linked Obsidian vault, then builds a queryable knowledge graph with [Graphify](https://github.com/Graphify-Labs/graphify).

```
$ cortex build ~/Documents/loose-notes

Triage: 142 files -> 89 kept, 53 dropped (51 by heuristic, 2 by LLM)
Vault generated: 89 notes in cortex-out/vault/
Building the graph (graphify)...
Graph complete: cortex-out/vault/graphify-out/
  graph.html      - interactive graph, open in a browser
  GRAPH_REPORT.md - audit report
  graph.json      - raw graph data

$ cortex query "which notes talk about the infrastructure budget?"
...
```

## What cortex does

- **Triage** - walks the input folder, drops obvious noise for free (build artifacts, lockfiles, oversized low-information data dumps) with a cheap heuristic pass, then asks an LLM to judge only the genuinely ambiguous files. Nothing gets silently dropped on an LLM failure - it defaults to keeping the file.
- **Vault generation** - for every file kept, an LLM writes a curated Obsidian-style note (summary, tags, cleaned-up body) and proposes real `[[wikilinks]]` between notes, written as explicit prose sentences rather than bare bracketed lists. A deterministic pass then guarantees zero dangling links in the final vault.
- **Graph build** - hands the resulting vault to [Graphify](https://github.com/Graphify-Labs/graphify), an existing separate tool, to produce a queryable knowledge graph (`graphify query "..."`, HTML visualization, audit report). Cortex orchestrates Graphify rather than reimplementing it.

## Requirements

- Python 3.10+
- An API key - [Anthropic](https://console.anthropic.com/) (default), or any OpenAI-compatible endpoint (local or cloud [Ollama](https://ollama.com), vLLM, LM Studio, ...) - **or**, with the `claude-cli` provider, a local [Claude Code](https://claude.com/claude-code) install authenticated to a Claude subscription, no API key needed (see Configuration below)
- [`graphifyy`](https://pypi.org/project/graphifyy/) (installed automatically as a dependency)

## Installation

### Automatic installation (recommended)

**macOS / Linux / Git Bash (Windows):**

```bash
curl -fsSL https://raw.githubusercontent.com/zomboky/cortex/main/install.sh | bash
```

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/zomboky/cortex/main/install.ps1 | iex
```

The script installs cortex globally with `uv tool install` (falling back to `pipx`, then `pip --user` if neither is available), the same way `graphifyy` itself is distributed.

### Manual installation

1. Clone the repo and install it in editable mode:
   ```bash
   git clone https://github.com/zomboky/cortex.git
   cd cortex
   pip install -e .
   ```
2. Verify:
   ```bash
   cortex --version
   ```

## Configuration

Cortex and Graphify have completely independent LLM configuration - Graphify only ever reads `GEMINI_API_KEY`/`GOOGLE_API_KEY`, never the variables below.

- `CORTEX_PROVIDER` - `anthropic` (default), `claude-cli`, or `openai-compatible`
- `CORTEX_API_KEY` - your API key (falls back to `ANTHROPIC_API_KEY` when provider is `anthropic`; unused/not required for `claude-cli`)
- `CORTEX_BASE_URL` - endpoint URL for `openai-compatible` (local or cloud Ollama, vLLM, ...)
- `CORTEX_MODEL` - default model for both stages
- `CORTEX_TRIAGE_MODEL` / `CORTEX_VAULT_MODEL` - override the model per stage (defaults: a cheap model for triage, a stronger one for vault generation, on Anthropic and claude-cli; required explicitly on `openai-compatible` since model names aren't standardized)
- `CORTEX_BATCH_SIZE` - files per triage LLM call (default 15)

Optional config file instead of env vars: `~/.config/cortex/config.toml` (`%APPDATA%\cortex\config.toml` on Windows). Run `cortex config init` to generate a starter file, and `cortex config show` to see the resolved configuration (the API key is never printed, only whether it's set).

### `claude-cli` provider (use your Claude subscription, no API key)

Instead of hitting the Anthropic API directly with a billed API key, `CORTEX_PROVIDER=claude-cli`
shells out to a local [Claude Code](https://claude.com/claude-code) install (`claude -p ...`) for
every LLM call. Claude Code's own auth (an OAuth session tied to a Claude subscription) is reused
as-is, so usage counts against that subscription instead of separate pay-per-token API credits.

Requirements:
- `claude` must be on `PATH` and already authenticated (`claude auth login`, or any working
  Claude Code session) on the machine running cortex.
- No `CORTEX_API_KEY`/`ANTHROPIC_API_KEY` needed.

```powershell
$env:CORTEX_PROVIDER = "claude-cli"
$env:CORTEX_MODEL = "claude-sonnet-5"   # same model names as the anthropic provider
```

Trade-offs versus the `anthropic` provider: each LLM call spawns a `claude -p` subprocess (higher
per-call latency than a direct API request), and throughput is bound by whatever session/rate
limits apply to the underlying subscription rather than API rate limits.

## Staying up to date

Cortex isn't published on PyPI: every install (`uv tool`, `pipx`, `pip --user`, or an editable
`pip install -e .` clone) resolves `git+https://github.com/zomboky/cortex.git` at install time, so
there's no PyPI-style version number to track -- the latest commit on `main` **is** the latest
version.

Every `cortex` invocation checks (at most once every 24h, cached) whether `main` has moved past the
commit it was installed from, and prints a notice if so. It never applies the update automatically:
doing so would mean the running process replaces its own venv/executable while it's still executing
them, which reliably fails on Windows (the interpreter locks its own files) and can leave the
install half-removed.

Run `cortex update` to actually apply it (whenever no `cortex` process is running) -- via `git pull
--ff-only` for an editable dev install (skipped if that checkout has uncommitted local changes, to
avoid clobbering work in progress), or by re-running the same `uv tool install` / `pipx install` /
`pip install --user` used originally otherwise. Set `CORTEX_SKIP_UPDATE_CHECK=1` to disable the check
entirely (no network call at all).

## Incremental caching

Re-running `cortex build`/`vault` on a folder you've already processed does not re-triage or
re-generate everything from scratch. Each file's content hash is tracked in `<output>/.cortex/`
(`triage-cache.json`, `vault-cache.json`, `graphify-cache.json`); a file whose hash hasn't changed
since the last run reuses its previous triage decision and note instead of calling the LLM again. A
file modified since the last run (different hash) is treated as new. If nothing in the vault changed,
the linking pass and the Graphify rebuild are skipped too -- both also cost LLM tokens (Graphify's own
semantic extraction included). `.cortex/` is specific to one `--output` directory; delete it to force
a full rebuild from scratch.

## Customizing

- Triage thresholds (size ceilings, entropy bands used to catch noise like an oversized low-information data dump): [`src/cortex/triage/heuristics.py`](src/cortex/triage/heuristics.py)
- Vault-generation and linking prompts: [`src/cortex/vault/generator.py`](src/cortex/vault/generator.py)
- Triage batch size: `--batch-size` flag or `CORTEX_BATCH_SIZE`

## Uninstalling

```bash
uv tool uninstall cortex   # or: pipx uninstall cortex
```

Remove `~/.config/cortex/config.toml` (or `%APPDATA%\cortex\config.toml`) if you created one.

## License

MIT

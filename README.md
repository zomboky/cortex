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
- An API key - [Anthropic](https://console.anthropic.com/) (default), or any OpenAI-compatible endpoint (local or cloud [Ollama](https://ollama.com), vLLM, LM Studio, ...)
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

- `CORTEX_PROVIDER` - `anthropic` (default) or `openai-compatible`
- `CORTEX_API_KEY` - your API key (falls back to `ANTHROPIC_API_KEY` when provider is `anthropic`)
- `CORTEX_BASE_URL` - endpoint URL for `openai-compatible` (local or cloud Ollama, vLLM, ...)
- `CORTEX_MODEL` - default model for both stages
- `CORTEX_TRIAGE_MODEL` / `CORTEX_VAULT_MODEL` - override the model per stage (defaults: a cheap model for triage, a stronger one for vault generation, on Anthropic; required explicitly on `openai-compatible` since model names aren't standardized)
- `CORTEX_BATCH_SIZE` - files per triage LLM call (default 15)

Optional config file instead of env vars: `~/.config/cortex/config.toml` (`%APPDATA%\cortex\config.toml` on Windows). Run `cortex config init` to generate a starter file, and `cortex config show` to see the resolved configuration (the API key is never printed, only whether it's set).

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

# Decision-First Positioning Operator

A terminal-first writing agent that produces sellable UX, marketing, and positioning content. All content modes (landing, LinkedIn, UX pack) are driven by **extracted positioning decisions** from your brief—so messaging stays sharp and consistent.

## Quickstart

1. Install and run [Ollama](https://ollama.com) with `llama3:8b`.
2. From the repo root:
   ```bash
   python src/main.py --client demo --mode positioning
   python src/main.py --client demo --mode linkedin
   python src/main.py --client demo --mode landing
   python src/main.py --client demo --mode ux
   ```
3. Check outputs:
   ```bash
   ls -lt clients/demo/outputs | head
   ```

## Folder structure map

| Path | Purpose |
|------|---------|
| `src/main.py` | CLI orchestrator: brief loading, mode dispatch, output save, latest update, manifest append. |
| `src/agents/writing_agent.py` | Decision extraction + mode generators + validation/fallback logic. |
| `src/agent_loop.py` | Optional multi-agent loop flows. |
| `src/core/brief.py` | CLI args + brief loading/saving. |
| `src/core/output.py` | Versioned output path selection. |
| `clients/<client>/brief.json` | Saved client brief when using `--client`. |
| `clients/<client>/outputs/` | Versioned outputs, latest files, and `_manifest.jsonl`. |
| `outputs/<product-slug>/` | Output location when `--client` is not provided. |

## Example commands

```bash
python src/main.py --client demo --mode positioning
python src/main.py --client demo --mode linkedin
python src/main.py --client demo --mode landing
python src/main.py --client demo --mode ux

python src/main.py --brief briefs/sample.json --mode landing
python src/main.py --brief briefs/sample.json --mode ux
```

## Decision-first flow

- **Decision phase:** Extracts a strict set of positioning decisions (ICP, primary problem, current alternative, desired outcome, category frame, differentiation, anti-positioning) from the brief.
- **Expression phase:** Landing, LinkedIn, and UX pack generation use only those decisions plus tone.
- **Validation phase:** Output is validated for required headers and banned phrases; strict retry and rule-based fallback are applied when needed.

## Output locations

- With `--client demo`: `clients/demo/outputs/`
- Without `--client` and using `--brief`: `outputs/<product-slug>/`
- Each mode writes:
- Versioned file: `<mode>_vN.md`
- Latest file: `<mode>_latest.md`
- Manifest log: `_manifest.jsonl`

## DEBUG_DECISIONS

Set `DEBUG_DECISIONS=true` to print extracted positioning decisions in the terminal.

```bash
DEBUG_DECISIONS=true python src/main.py --client demo --mode linkedin
```

## Docs

- [docs/WALKTHROUGH.md](docs/WALKTHROUGH.md) — Folder map and how to read the latest output.
- [docs/PROMPTS.md](docs/PROMPTS.md) — Decisions → expression pattern and banned phrases.

## Constraints

- No external LLM APIs; uses local Ollama only.
- Terminal-first; no UI.
- Standard library + existing dependencies only.

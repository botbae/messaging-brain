# Decision-First Positioning Operator

Terminal-first writing system that enforces **positioning decisions first**, then generates outputs (LinkedIn, landing, UX pack) from those decisions.

## Quickstart

1) Ensure Ollama is running and you have the model:
```bash
ollama pull llama3:8b
```

2) Run any mode:
```bash
python src/main.py --client demo --mode positioning
python src/main.py --client demo --mode linkedin
python src/main.py --client demo --mode landing
python src/main.py --client demo --mode ux
```

## Where outputs are saved

With `--client demo`:
- Versioned: `clients/demo/outputs/<mode>_vN.md`
- Latest: `clients/demo/outputs/<mode>_latest.md`
- Manifest: `clients/demo/outputs/_manifest.jsonl`

## Useful flags

Print extracted decisions:
```bash
DEBUG_DECISIONS=true python src/main.py --client demo --mode linkedin
```

Enable agent loop (if supported by the selected mode):
```bash
AGENT_LOOP=true python src/main.py --client demo --mode linkedin
```

## Repo map

- `src/main.py` — CLI orchestrator (prints banner, saves version + latest, appends manifest)
- `src/agents/writing_agent.py` — decision extraction + generators + validators
- `src/core/brief.py` — brief loading (file/env/interactive) + `--client` sessions
- `clients/<client>/brief.json` — saved client brief
- `clients/<client>/outputs/` — outputs

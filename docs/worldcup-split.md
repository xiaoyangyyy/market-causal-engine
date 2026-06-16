# World Cup Legacy Split (Step D)

The **market event** product (`market_causal_engine/`) is the primary repository focus.  
The original **World Cup crowd-risk** prototype lives in `worldcup_causal_engine/` and is **legacy**.

## Why split?

- Reviewers conflate two research products (stadium crowd-risk vs earnings forensics)
- CI and README should lead with financial event intelligence
- World Cup code remains reproducible as a standalone historical project

## Export to standalone repo

```bash
python scripts/export_worldcup_legacy.py --output dist/worldcup-causal-engine
cd dist/worldcup-causal-engine
git init && git add . && git commit -m "Extract World Cup legacy from market-causal-engine"
# git remote add origin git@github.com:YOU/worldcup-causal-engine.git && git push -u origin main
```

The export includes:

- `worldcup_causal_engine/` package
- World Cup scenarios, interventions, priors, observations
- Legacy tests (`pytest-worldcup.ini`)
- Phase 1–4 docs and experiment scripts

## Monorepo policy (until physical split)

| Path | Status |
|------|--------|
| `market_causal_engine/` | **Primary** — active development |
| `worldcup_causal_engine/` | **Legacy** — maintenance only; separate CI job |
| `data/scenarios/` (S1–S6) | World Cup only |
| `data/market/` | Market product |

CI runs **market-test** (default) and **worldcup-legacy** (isolated) jobs.

## Killer demo (market product)

See [demo/README.md](../demo/README.md) — NFLX 2022 Q1 earnings forensics dashboard.

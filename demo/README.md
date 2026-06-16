# Killer Demo — NFLX 2022 Q1 Earnings

One-screen walkthrough for reviewers: **point-in-time evidence → mechanism path → econometric counterfactual → channel ablation**.

## Static (fastest — no extra deps)

```bash
python scripts/export_killer_demo.py
# Open demo/static/index.html in a browser
# Or serve locally:
python -m http.server 8765 --directory demo/static
```

## Streamlit (interactive)

```bash
pip install -e ".[demo]"
python scripts/run_killer_demo.py
```

## API

```bash
uvicorn market_causal_engine.api.app:app --port 8080
curl http://localhost:8080/demo/killer/nflx_2022q1_earnings
```

## What it shows

| Panel | Content |
|-------|---------|
| Event timeline | PIT-admissible atoms at `as_of=120` with `published_time` + source hash |
| Mechanism path | Dominant causal chain (subscriber miss → guidance → repricing…) |
| Counterfactual | CAR, synthetic control effect, placebo rank |
| Channel ablation | `no_sec` / `no_news` / `no_price` marginal contribution vs observed CAR |
| Neighbors | Similar historical case studies by path overlap |
| Caveats | Look-ahead rejects, non-advice disclaimer, model limits |

Built by `market_causal_engine/demo/killer_demo.py`.

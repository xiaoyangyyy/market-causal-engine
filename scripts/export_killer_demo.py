#!/usr/bin/env python3
"""Build killer demo JSON + static HTML (no Streamlit required)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from market_causal_engine.demo.killer_demo import DEFAULT_DEMO_CASE, build_killer_demo

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Market Causal Engine — Killer Demo</title>
  <style>
    :root { --bg:#0f1419; --card:#1a2332; --text:#e7ecf3; --muted:#8b9cb3; --accent:#3d8bfd; --down:#f85149; --up:#3fb950; }
    * { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 1.5rem; line-height: 1.5; }
    h1 { font-size: 1.5rem; margin: 0 0 .25rem; }
    .tagline { color: var(--muted); margin-bottom: 1.5rem; }
    .grid { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
    .card { background: var(--card); border-radius: 8px; padding: 1rem 1.25rem; border: 1px solid #2d3a4f; }
    .card h2 { font-size: .85rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 0 0 .75rem; }
    .metric { font-size: 1.75rem; font-weight: 600; }
    .metric.down { color: var(--down); }
    .path-step { padding: .35rem 0; border-left: 3px solid var(--accent); padding-left: .75rem; margin: .35rem 0; }
    .atom { font-size: .85rem; border-bottom: 1px solid #2d3a4f; padding: .5rem 0; }
    .atom-meta { color: var(--muted); font-size: .75rem; }
    .chip { display: inline-block; background: #243044; padding: .15rem .5rem; border-radius: 4px; font-size: .75rem; margin-right: .35rem; }
    ul.caveats { margin: 0; padding-left: 1.2rem; color: var(--muted); font-size: .9rem; }
    table { width: 100%; border-collapse: collapse; font-size: .85rem; }
    td, th { text-align: left; padding: .35rem .5rem; border-bottom: 1px solid #2d3a4f; }
  </style>
</head>
<body>
  <h1 id="title">Loading…</h1>
  <p class="tagline" id="tagline"></p>
  <div class="grid" id="metrics"></div>
  <div class="grid" style="margin-top:1rem">
    <div class="card" style="grid-column: 1 / -1"><h2>Mechanism path</h2><div id="path"></div></div>
    <div class="card"><h2>Event timeline (PIT admissible)</h2><div id="timeline"></div></div>
    <div class="card"><h2>Channel ablation vs CAR</h2><div id="ablation"></div></div>
    <div class="card"><h2>Similar historical cases</h2><div id="neighbors"></div></div>
    <div class="card" style="grid-column: 1 / -1"><h2>Limitations &amp; caveats</h2><ul class="caveats" id="caveats"></ul></div>
  </div>
  <script>
    fetch('__JSON_FILE__').then(r => r.json()).then(d => {
      document.getElementById('title').textContent = d.hero.title;
      document.getElementById('tagline').textContent = d.hero.tagline + ' · as_of=' + d.as_of_minutes + 'min';
      const es = d.counterfactual.event_study || {};
      const obs = d.counterfactual.observed || {};
      const mod = d.counterfactual.model || {};
      document.getElementById('metrics').innerHTML = [
        ['Observed AH', (obs.after_hours_return_pct || '—') + '%', 'down'],
        ['CAR (econometric)', (es.CAR_pct || '—') + '%', 'down'],
        ['Model direction', mod.simulated_direction || '—', mod.simulated_direction === 'down' ? 'down' : ''],
        ['Dominant channel', d.dominant_channel || '—', ''],
      ].map(([l,v,c]) => '<div class="card"><h2>'+l+'</h2><div class="metric '+c+'">'+v+'</div></div>').join('');
      document.getElementById('path').innerHTML = (d.mechanism_path.narrative || []).map(s =>
        '<div class="path-step">'+s+'</div>').join('') || '<em>No path</em>';
      document.getElementById('timeline').innerHTML = (d.event_timeline || []).map(a =>
        '<div class="atom"><div class="atom-meta">t='+a.minute+' · '+a.source+' · '+a.source_class+'</div>'+a.text+'</div>').join('');
      const ch = d.channel_ablation || {};
      document.getElementById('ablation').innerHTML = '<table><tr><th>Channel</th><th>Marginal</th><th>Share of CAR</th></tr>' +
        Object.entries(ch).map(([k,v]) => '<tr><td>'+k+'</td><td>'+(v.marginal_return_pct||'—')+'pp</td><td>'+(v.share_of_observed_car||'—')+'</td></tr>').join('') + '</table>';
      document.getElementById('neighbors').innerHTML = (d.benchmark_neighbors || []).map(n =>
        '<div class="atom"><span class="chip">'+n.ticker+'</span> '+n.case_id+' <span class="atom-meta">score '+n.similarity_score+'</span></div>').join('');
      document.getElementById('caveats').innerHTML = (d.limitations || []).map(x => '<li>'+x+'</li>').join('');
    });
  </script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", default=DEFAULT_DEMO_CASE)
    parser.add_argument("--as-of", type=int, default=120)
    parser.add_argument("--out-dir", default=str(ROOT / "demo" / "static"))
    args = parser.parse_args()

    payload = build_killer_demo(args.case, as_of=args.as_of)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_name = f"{args.case}.json"
    json_path = out / json_name
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    html = HTML_TEMPLATE.replace("__JSON_FILE__", json_name)
    html_path = out / "index.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {html_path}")
    print("Open demo/static/index.html in a browser (or: python -m http.server --directory demo/static)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

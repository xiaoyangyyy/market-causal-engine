# Calibration Report: S2_team_eliminated_transit_delay

- Generated: 2026-06-05T08:14:34.235406+00:00
- Observations: `E:\ca\data\observations\real_qatar2022_S2_w0.jsonl`
- Search trials: 80
- Best loss: **0.103128335**

## Best prior overrides
```json
{
  "fans_gather": {
    "density_delta": 0.22574437556463683,
    "pressure_delta": 0.17474982940417694
  },
  "opposing_fans_contact": {
    "emit_conflict_delay": 5.997683630234599
  },
  "verbal_conflict": {
    "verbal_risk_delta": 0.12317006659767503
  }
}
```

## Loss breakdown
```json
{
  "total": 0.103128335,
  "items": [
    {
      "key": "verbal_conflict",
      "pred": 0.2217,
      "obs": 0.22,
      "weight": 1.5,
      "squared_error": 2.890000000000024e-06,
      "weighted_error": 4.3350000000000356e-06
    },
    {
      "key": "scuffle",
      "pred": 0.378,
      "obs": 0.06,
      "weight": 1.0,
      "squared_error": 0.101124,
      "weighted_error": 0.101124
    },
    {
      "key": "panic",
      "pred": 0.0,
      "obs": 0.05,
      "weight": 0.8,
      "squared_error": 0.0025000000000000005,
      "weighted_error": 0.0020000000000000005
    }
  ]
}
```

## Baseline vs calibrated final risk
- Baseline: `{'verbal_conflict': 0.72, 'scuffle': 0.378, 'riot': 0.0, 'panic': 0.0}`
- Calibrated: `{'verbal_conflict': 0.2217, 'scuffle': 0.378, 'riot': 0.0, 'panic': 0.0}`

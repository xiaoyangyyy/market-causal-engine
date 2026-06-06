# Calibration Report: S1_controversial_call_high_density

- Generated: 2026-06-05T12:04:23.609746+00:00
- Observations: `E:\ca\data\observations\real_qatar2022_S1_w0.jsonl`
- Search trials: 300
- Best loss: **0.0010293599999999985**

## Best prior overrides
```json
{
  "rumor_amplified": {
    "rumor_delta": 0.9994977278889086
  },
  "offline_mood_shift": {
    "verbal_risk_delta": 0.10196303435879471
  },
  "opposing_fans_contact": {
    "emit_conflict_delay": 24.286913917549278,
    "colocation_threshold_crowd": 0.920546793203251
  },
  "verbal_conflict": {
    "verbal_risk_delta": 0.13033044547385972,
    "scuffle_risk_delta": 0.021641777742273983
  }
}
```

## Loss breakdown
```json
{
  "total": 0.0010293599999999985,
  "items": [
    {
      "key": "rumor_volume_index",
      "pred": 0.7996,
      "obs": 0.82,
      "weight": 1.5,
      "squared_error": 0.0004161599999999989,
      "weighted_error": 0.0006242399999999983
    },
    {
      "key": "verbal_conflict",
      "pred": 0.0816,
      "obs": 0.08,
      "weight": 2.0,
      "squared_error": 2.5600000000000136e-06,
      "weighted_error": 5.120000000000027e-06
    },
    {
      "key": "scuffle",
      "pred": 0.0,
      "obs": 0.02,
      "weight": 1.0,
      "squared_error": 0.0004,
      "weighted_error": 0.0004
    },
    {
      "key": "riot",
      "pred": 0.0,
      "obs": 0.0,
      "weight": 1.0,
      "squared_error": 0.0,
      "weighted_error": 0.0
    }
  ]
}
```

## Baseline vs calibrated final risk
- Baseline: `{'verbal_conflict': 0.52, 'scuffle': 0.12, 'riot': 0.0, 'panic': 0.0}`
- Calibrated: `{'verbal_conflict': 0.0816, 'scuffle': 0.0, 'riot': 0.0, 'panic': 0.0}`

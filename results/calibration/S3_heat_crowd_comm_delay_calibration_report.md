# Calibration Report: S3_heat_crowd_comm_delay

- Generated: 2026-06-05T08:14:34.418920+00:00
- Observations: `E:\ca\data\observations\real_qatar2022_S3_w0.jsonl`
- Search trials: 80
- Best loss: **0.138862408**

## Best prior overrides
```json
{
  "crowd_push": {
    "panic_delta": 0.12727282365213818
  },
  "panic_signal": {
    "panic_delta": 0.11884655016989383
  },
  "fans_gather": {
    "pressure_delta": 0.07192982607013183
  },
  "verbal_conflict": {
    "verbal_risk_delta": 0.238233812510927
  }
}
```

## Loss breakdown
```json
{
  "total": 0.138862408,
  "items": [
    {
      "key": "panic",
      "pred": 0.4922,
      "obs": 0.48,
      "weight": 2.0,
      "squared_error": 0.00014884000000000108,
      "weighted_error": 0.00029768000000000215
    },
    {
      "key": "verbal_conflict",
      "pred": 0.2382,
      "obs": 0.12,
      "weight": 1.2,
      "squared_error": 0.01397124,
      "weighted_error": 0.016765488
    },
    {
      "key": "scuffle",
      "pred": 0.27,
      "obs": 0.08,
      "weight": 1.0,
      "squared_error": 0.0361,
      "weighted_error": 0.0361
    },
    {
      "key": "riot",
      "pred": 0.2,
      "obs": 0.05,
      "weight": 0.8,
      "squared_error": 0.022500000000000006,
      "weighted_error": 0.018000000000000006
    },
    {
      "key": "riot",
      "pred": 0.2,
      "obs": 0.02,
      "weight": 1.5,
      "squared_error": 0.032400000000000005,
      "weighted_error": 0.048600000000000004
    },
    {
      "key": "verbal_conflict",
      "pred": 0.2382,
      "obs": 0.1,
      "weight": 1.0,
      "squared_error": 0.019099239999999996,
      "weighted_error": 0.019099239999999996
    }
  ]
}
```

## Baseline vs calibrated final risk
- Baseline: `{'verbal_conflict': 0.4, 'scuffle': 0.27, 'riot': 0.2, 'panic': 1.0}`
- Calibrated: `{'verbal_conflict': 0.2382, 'scuffle': 0.27, 'riot': 0.2, 'panic': 0.4922}`

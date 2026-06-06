"""Generate sample_match_feed.jsonl for Phase 3 demos."""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "atoms" / "sample_match_feed.jsonl"

TEXTS = {
    "blame_referee": [
        "The ref robbed us.",
        "Blatant penalty miss!",
        "Worst officiating ever.",
        "Referee is blind.",
        "How was that not a foul?",
    ],
    "rumor_clip_shared": [
        "Watch this clip!!!",
        "They don't want you to see this angle",
        "Viral moment from the match",
        "Share before they delete it",
    ],
    "defend_referee": [
        "Ref made the right call.",
        "Play was onside, calm down.",
        "Stop blaming the ref.",
    ],
    "fan_conflict_report": [
        "Fans fighting outside the bar!",
        "Two groups shouting at each other near fan zone",
        "Almost a scuffle on the street",
    ],
}


def main() -> None:
    atoms: list[dict] = []
    n = 0

    for i in range(220):
        n += 1
        base = TEXTS["blame_referee"][i % len(TEXTS["blame_referee"])]
        atoms.append({
            "atom_id": f"A{n}",
            "source_id": f"post_{i % 45}",
            "time": 70 + (i % 10),
            "claim_type": "blame_referee",
            "target": "referee",
            "actor_group": "Team_A_fans",
            "emotion": "anger",
            "confidence": 0.75 + (i % 10) * 0.02,
            "raw_text": f"{base} #{i}",
        })

    for i in range(55):
        n += 1
        base = TEXTS["rumor_clip_shared"][i % len(TEXTS["rumor_clip_shared"])]
        atoms.append({
            "atom_id": f"A{n}",
            "source_id": f"clip_{i % 35}",
            "time": 71 + (i % 8),
            "claim_type": "rumor_clip_shared",
            "target": "referee",
            "actor_group": "social_users",
            "emotion": "rage",
            "confidence": 0.7,
            "raw_text": f"{base} #{i}",
        })

    for i in range(8):
        n += 1
        atoms.append({
            "atom_id": f"A{n}",
            "source_id": f"defend_{i % 12}",
            "time": 72 + (i % 6),
            "claim_type": "defend_referee",
            "target": "referee",
            "actor_group": "Team_B_fans",
            "emotion": "neutral",
            "confidence": 0.65,
            "raw_text": TEXTS["defend_referee"][i % len(TEXTS["defend_referee"])],
        })

    for i in range(12):
        n += 1
        atoms.append({
            "atom_id": f"A{n}",
            "source_id": f"witness_{i % 8}",
            "time": 95 + (i % 5),
            "claim_type": "fan_conflict_report",
            "target": "fan_zone",
            "actor_group": "local_residents",
            "emotion": "fear",
            "confidence": 0.8,
            "raw_text": TEXTS["fan_conflict_report"][i % len(TEXTS["fan_conflict_report"])],
        })

    atoms.sort(key=lambda a: (a["time"], a["atom_id"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for atom in atoms:
            f.write(json.dumps(atom, ensure_ascii=False) + "\n")
    print(f"Wrote {len(atoms)} atoms to {OUT}")


if __name__ == "__main__":
    main()

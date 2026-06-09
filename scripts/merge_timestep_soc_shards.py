#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

CST = ZoneInfo("Asia/Shanghai")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge timestep SOC scan shard outputs.")
    parser.add_argument("--shards-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--num-shards", type=int, required=True)
    return parser.parse_args()


def read_required_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_frames: list[pd.DataFrame] = []
    event_frames: list[pd.DataFrame] = []
    scenario_frames: list[pd.DataFrame] = []
    shard_metadata: list[dict[str, object]] = []

    for shard_index in range(args.num_shards):
        shard_dir = args.shards_root / f"shard_{shard_index}"
        run_frames.append(read_required_csv(shard_dir / "run_summary.csv"))
        events_path = shard_dir / "avalanche_events.csv"
        if events_path.exists() and events_path.stat().st_size > 1:
            event_frames.append(pd.read_csv(events_path))
        scenario_frames.append(read_required_csv(shard_dir / "scenario_summary.csv"))
        metadata_path = shard_dir / "metadata.json"
        if metadata_path.exists():
            shard_metadata.append(json.loads(metadata_path.read_text(encoding="utf-8")))

    runs = pd.concat(run_frames, ignore_index=True).sort_values(
        ["scenario_index", "scenario_id", "run_index"]
    )
    if event_frames:
        events = pd.concat(event_frames, ignore_index=True).sort_values(
            ["scenario_index", "scenario_id", "run_index", "avalanche_index"]
        )
    else:
        events = pd.DataFrame()
    scenario_summary = pd.concat(scenario_frames, ignore_index=True).sort_values(
        ["scenario_index", "scenario_id"]
    )

    run_summary_csv = args.output_dir / "run_summary.csv"
    avalanche_csv = args.output_dir / "avalanche_events.csv"
    scenario_summary_csv = args.output_dir / "scenario_summary.csv"
    runs.to_csv(run_summary_csv, index=False)
    events.to_csv(avalanche_csv, index=False)
    scenario_summary.to_csv(scenario_summary_csv, index=False)

    metadata = {
        "created_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "protocol": "timestep_settle_check",
        "shards_root": str(args.shards_root),
        "num_shards": args.num_shards,
        "run_count": int(len(runs)),
        "event_count": int(len(events)),
        "scenario_count": int(scenario_summary["scenario_id"].nunique()),
        "scenario_base_count": int(scenario_summary["scenario_base_id"].nunique()),
        "run_summary_csv": str(run_summary_csv),
        "avalanche_csv": str(avalanche_csv),
        "scenario_summary_csv": str(scenario_summary_csv),
        "shard_metadata": shard_metadata,
    }
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

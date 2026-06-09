#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "scripts"))
from run_comprehensive_scenario_scan import aggregate_scenarios

CST = ZoneInfo("Asia/Shanghai")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge period critical refined scan shards.")
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def read_many(name: str, shard_dirs: list[Path]) -> pd.DataFrame:
    frames = []
    for shard in shard_dirs:
        path = shard / name
        if path.exists() and path.stat().st_size > 0:
            frames.append(pd.read_csv(path))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main() -> None:
    args = parse_args()
    shard_dirs = sorted(path for path in args.input_root.glob("shard_*") if path.is_dir())
    if not shard_dirs:
        raise FileNotFoundError(f"no shard_* directories under {args.input_root}")
    missing = [
        str(path)
        for shard in shard_dirs
        for path in [shard / "run_summary.csv", shard / "avalanche_events.csv"]
        if not path.exists()
    ]
    if missing:
        raise FileNotFoundError("missing shard outputs: " + ", ".join(missing[:10]))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    runs = read_many("run_summary.csv", shard_dirs)
    events = read_many("avalanche_events.csv", shard_dirs)
    if not events.empty and "propagated_default_count" not in events:
        events["propagated_default_count"] = (
            events["collapse_size"] - events["initial_default_count"]
        ).clip(lower=0)
    scenarios = aggregate_scenarios(runs, events)
    scenarios["protocol"] = "period_end_critical_refined"

    runs = runs.sort_values(["scenario_index", "scenario_id", "run_index"])
    if not events.empty:
        events = events.sort_values(["scenario_index", "scenario_id", "run_index", "avalanche_index"])
    scenarios = scenarios.sort_values(["scenario_base_id", "c"])

    runs.to_csv(args.output_dir / "run_summary.csv", index=False)
    events.to_csv(args.output_dir / "avalanche_events.csv", index=False)
    scenarios.to_csv(args.output_dir / "scenario_summary.csv", index=False)

    candidate_tables = [
        pd.read_csv(path)
        for path in sorted(args.input_root.glob("shard_*/selected_critical_band_bases.csv"))
        if path.exists()
    ]
    if candidate_tables:
        pd.concat(candidate_tables, ignore_index=True).drop_duplicates("scenario_base_id").to_csv(
            args.output_dir / "selected_critical_band_bases.csv", index=False
        )

    shard_meta = []
    for shard in shard_dirs:
        meta_path = shard / "metadata.json"
        if meta_path.exists():
            shard_meta.append(json.loads(meta_path.read_text(encoding="utf-8")))
    metadata = {
        "created_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "input_root": str(args.input_root),
        "output_dir": str(args.output_dir),
        "shards": [str(path) for path in shard_dirs],
        "shard_count": len(shard_dirs),
        "run_count": int(len(runs)),
        "event_count": int(len(events)),
        "scenario_count": int(scenarios["scenario_id"].nunique()) if len(scenarios) else 0,
        "scenario_base_count": int(scenarios["scenario_base_id"].nunique()) if len(scenarios) else 0,
        "shard_metadata": shard_meta,
    }
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""CLI for production platform operations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from market_causal_engine.platform.backfill import BACKFILL_HANDLERS, BackfillRunner
from market_causal_engine.platform.pipeline import DailyPipeline
from market_causal_engine.platform.storage.factory import get_platform_store


def cmd_run_daily(args: argparse.Namespace) -> int:
    pipeline = DailyPipeline(store_root=Path(args.store) if args.store else None)
    result = pipeline.run(
        as_of_time=args.as_of,
        tickers=args.ticker or [],
        skip_network_ingest=args.offline,
        replay_cases=not args.no_replay,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0 if result.status == "succeeded" else 1


def cmd_health_report(args: argparse.Namespace) -> int:
    storage = get_platform_store(store_root=Path(args.store) if args.store else None)
    report = storage.freshness_report()
    manifest = storage.load_manifest(args.run_id) if args.run_id else None
    out = {"freshness": report}
    if manifest:
        out["run"] = manifest.to_dict()
    print(json.dumps(out, indent=2))
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    store = get_platform_store(store_root=Path(args.store) if args.store else None)
    store.ensure_schema()
    backend = store.freshness_report().get("backend", "unknown")
    print(json.dumps({"status": "ok", "backend": backend}, indent=2))
    return 0


def cmd_backfill_start(args: argparse.Namespace) -> int:
    runner = BackfillRunner(get_platform_store(store_root=Path(args.store) if args.store else None))
    job = runner.start(
        args.job_type,
        tickers=args.ticker or None,
        batch_size=args.batch_size,
        resume_job_id=args.resume,
    )
    print(json.dumps(job.to_dict(), indent=2))
    return 0 if job.status == "succeeded" else 1


def cmd_backfill_status(args: argparse.Namespace) -> int:
    runner = BackfillRunner(get_platform_store(store_root=Path(args.store) if args.store else None))
    if args.list:
        jobs = runner.list_jobs(status=args.status, limit=args.limit)
        print(json.dumps([j.to_dict() for j in jobs], indent=2))
        return 0
    job = runner.status(args.job_id)
    if not job:
        print(json.dumps({"error": f"job not found: {args.job_id}"}), file=sys.stderr)
        return 1
    print(json.dumps(job.to_dict(), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Market Causal Engine — production platform")
    sub = parser.add_subparsers(dest="command", required=True)

    daily = sub.add_parser("run-daily", help="Run daily ingest → store → replay pipeline")
    daily.add_argument("--as-of", default=None, help="ISO8601 as-of time (default: now UTC)")
    daily.add_argument("--ticker", action="append", default=[], help="Filter ingest by ticker")
    daily.add_argument("--store", default=None, help="Platform store root path")
    daily.add_argument("--offline", action="store_true", help="Skip network ingestors")
    daily.add_argument("--no-replay", action="store_true", help="Skip case replay stage")
    daily.set_defaults(func=cmd_run_daily)

    health = sub.add_parser("health-report", help="Data freshness + optional run manifest")
    health.add_argument("--store", default=None)
    health.add_argument("--run-id", default=None)
    health.set_defaults(func=cmd_health_report)

    migrate = sub.add_parser("migrate", help="Apply database schema (Postgres) or init local store")
    migrate.add_argument("--store", default=None)
    migrate.set_defaults(func=cmd_migrate)

    bf = sub.add_parser("backfill", help="Resumable backfill jobs")
    bf_sub = bf.add_subparsers(dest="backfill_cmd", required=True)

    bf_start = bf_sub.add_parser("start", help="Start or resume backfill")
    bf_start.add_argument("job_type", choices=list(BACKFILL_HANDLERS.keys()))
    bf_start.add_argument("--ticker", action="append", default=[])
    bf_start.add_argument("--batch-size", type=int, default=1)
    bf_start.add_argument("--resume", default=None, help="Resume existing job_id")
    bf_start.add_argument("--store", default=None)
    bf_start.set_defaults(func=cmd_backfill_start)

    bf_status = bf_sub.add_parser("status", help="Job status")
    bf_status.add_argument("job_id", nargs="?", default=None)
    bf_status.add_argument("--list", action="store_true")
    bf_status.add_argument("--status", default=None)
    bf_status.add_argument("--limit", type=int, default=20)
    bf_status.add_argument("--store", default=None)
    bf_status.set_defaults(func=cmd_backfill_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

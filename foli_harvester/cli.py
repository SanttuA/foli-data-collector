from __future__ import annotations

import argparse
import logging
import sys
import time

from .collector import Collector
from .config import Config
from .db import connect_database
from .health import run_healthcheck
from .storage import Storage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="foli_harvester")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db", help="Create or update database schema.")
    subparsers.add_parser("collect", help="Run the long-lived collector loop.")
    subparsers.add_parser("fetch-gtfs-once", help="Download and archive one GTFS zip.")
    subparsers.add_parser("healthcheck", help="Check database, state, lock, and GTFS directory.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = Config.from_env()

    if args.command == "init-db":
        conn = connect_database(config.database_url, config.auth_token)
        Storage(conn).init_schema()
        if hasattr(conn, "close"):
            conn.close()
        print("database schema ready")
        return 0

    if args.command == "collect":
        return _run_collect_with_startup_retry(config)

    if args.command == "fetch-gtfs-once":
        collector = Collector(config)
        collector.storage.init_schema()
        if not collector.lock.acquire():
            current = collector.storage.get_lock(collector.lock.lock_name)
            owner = current["owner_id"] if current else "unknown"
            print(f"collector lock is owned by {owner}; not fetching GTFS", file=sys.stderr)
            return 2
        try:
            collector.collect_gtfs()
        finally:
            collector.lock.release()
            if hasattr(collector.conn, "close"):
                collector.conn.close()
        return 0

    if args.command == "healthcheck":
        ok, errors = run_healthcheck(config)
        if ok:
            print("healthcheck ok")
            return 0
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    parser.error(f"unknown command {args.command}")
    return 2


def _run_collect_with_startup_retry(config: Config) -> int:
    while True:
        collector = None
        try:
            collector = Collector(config)
            return collector.run_forever()
        except KeyboardInterrupt:
            return 130
        except Exception as exc:
            logging.exception(
                "collector startup/runtime failed; retrying in %ss: %s",
                config.backoff_base_seconds,
                exc,
            )
            if collector is not None and hasattr(collector.conn, "close"):
                try:
                    collector.conn.close()
                except Exception:
                    logging.exception("failed to close collector database connection")
            time.sleep(config.backoff_base_seconds)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
WATCHLIST_FILE = BASE_DIR / "watchlist.json"


def load_watchlist() -> dict:
    return json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))


def active_items(watchlist: dict) -> list[dict]:
    return [
        item
        for item in watchlist.get("items", [])
        if str(item.get("status", "")).lower() == "active"
    ]


def run_item(item: dict, *, once: bool) -> int:
    config = item.get("config")
    if not config:
        print(f"[skip] {item.get('name', item.get('id'))}: missing config", flush=True)
        return 0

    cmd = [sys.executable, "goofish_monitor.py", "monitor", "--config", config]
    if once:
        cmd.append("--once")
    print(f"[run] {item.get('name', item.get('id'))}: {' '.join(cmd)}", flush=True)
    return subprocess.call(cmd, cwd=str(BASE_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all active Goofish watchlist items.")
    parser.add_argument("--once", action="store_true", help="Run every active item once and exit.")
    parser.add_argument("--sleep", type=int, default=900, help="Loop sleep seconds when --once is not set.")
    args = parser.parse_args()

    while True:
        watchlist = load_watchlist()
        items = active_items(watchlist)
        if not items:
            print("No active watchlist items.", flush=True)
            return 0

        exit_code = 0
        for item in items:
            exit_code = max(exit_code, run_item(item, once=True))

        if args.once:
            return exit_code
        print(f"[sleep] {args.sleep}s", flush=True)
        time.sleep(max(60, args.sleep))


if __name__ == "__main__":
    raise SystemExit(main())

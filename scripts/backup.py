"""Create a consistent SQLite + file backup on the already-encrypted backup volume."""
from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="data/app.db")
    parser.add_argument("--storage", default="storage")
    parser.add_argument("--destination", default="backups")
    args = parser.parse_args()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = Path(args.destination) / stamp
    target.mkdir(parents=True, exist_ok=False)
    with sqlite3.connect(args.database) as source, sqlite3.connect(target / "app.db") as dest:
        source.backup(dest)
    shutil.copytree(args.storage, target / "storage", dirs_exist_ok=True)

    backups = sorted(p for p in Path(args.destination).iterdir() if p.is_dir())
    daily_cutoff = datetime.now(UTC) - timedelta(days=7)
    weekly_cutoff = datetime.now(UTC) - timedelta(weeks=4)
    for path in backups:
        try:
            created = datetime.strptime(path.name, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        except ValueError:
            continue
        keep_daily = created >= daily_cutoff
        keep_weekly = created >= weekly_cutoff and created.weekday() == 0
        if not keep_daily and not keep_weekly:
            shutil.rmtree(path)
    print(target)


if __name__ == "__main__":
    main()


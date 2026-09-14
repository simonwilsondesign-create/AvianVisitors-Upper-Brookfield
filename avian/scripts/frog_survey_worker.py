#!/usr/bin/env python3
"""Archive completed BirdNET recordings for a short native-frog survey.

This is deliberately a collection tool, not a species recogniser. It keeps
night recordings in a compact, reviewable FLAC archive while BirdNET remains
the only process using the microphone.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Australia/Brisbane")
STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2})-birdnet-(\d{2}:\d{2}:\d{2})\.wav$")


def recording_time(path: Path) -> dt.datetime | None:
    match = STAMP.match(path.name)
    if not match:
        return None
    try:
        return dt.datetime.strptime(" ".join(match.groups()), "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
    except ValueError:
        return None


def in_survey_window(at: dt.datetime) -> bool:
    """Collect dusk through early morning, when local frogs most often call."""
    return at.hour >= 17 or at.hour < 9


def initialise(db: sqlite3.Connection) -> None:
    db.execute("CREATE TABLE IF NOT EXISTS processed (recording TEXT PRIMARY KEY, processed_at TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS archive (recording TEXT PRIMARY KEY, recorded_at TEXT NOT NULL, path TEXT NOT NULL, bytes INTEGER NOT NULL)")
    db.commit()


def archive(recording: Path, recorded_at: dt.datetime, root: Path, ffmpeg: str) -> Path:
    destination = root / recorded_at.strftime("%Y-%m-%d") / recording.with_suffix(".flac").name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        return destination
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".frog-", suffix=".flac", delete=False) as temp:
        temporary = Path(temp.name)
    try:
        subprocess.run([
            ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(recording),
            "-vn", "-ac", "1", "-ar", "48000", "-c:a", "flac", "-compression_level", "5", str(temporary),
        ], check=True, timeout=90)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def prune(root: Path, db: sqlite3.Connection, keep_days: int, now: dt.datetime) -> int:
    cutoff = (now - dt.timedelta(days=keep_days)).date()
    removed = 0
    for child in root.iterdir() if root.is_dir() else []:
        if not child.is_dir():
            continue
        try:
            day = dt.date.fromisoformat(child.name)
        except ValueError:
            continue
        if day >= cutoff:
            continue
        shutil.rmtree(child)
        removed += 1
    db.execute("DELETE FROM archive WHERE recorded_at < ?", (dt.datetime.combine(cutoff, dt.time(), TZ).isoformat(),))
    db.commit()
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recordings", type=Path, default=Path("/home/pi/BirdSongs/StreamData"))
    parser.add_argument("--state", type=Path, default=Path("/var/lib/avian-frog/state.sqlite"))
    parser.add_argument("--archive", type=Path, default=Path("/var/lib/avian-frog/recordings"))
    parser.add_argument("--ffmpeg", default="/usr/bin/ffmpeg")
    parser.add_argument("--keep-days", type=int, default=7)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    now = dt.datetime.now(TZ)
    args.state.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(args.state)
    initialise(db)
    saved = skipped = 0
    for recording in sorted(args.recordings.glob("*.wav"), key=lambda item: item.stat().st_mtime):
        if db.execute("SELECT 1 FROM processed WHERE recording = ?", (recording.name,)).fetchone():
            continue
        # A complete 15-second 48 kHz WAV is well above this size. Never copy
        # the current chunk while the recorder is still writing it.
        if recording.stat().st_size < 2_000_000:
            continue
        recorded_at = recording_time(recording)
        if recorded_at is None or not in_survey_window(recorded_at):
            skipped += 1
        elif args.dry_run:
            saved += 1
        else:
            target = archive(recording, recorded_at, args.archive, args.ffmpeg)
            db.execute("INSERT OR REPLACE INTO archive (recording, recorded_at, path, bytes) VALUES (?, ?, ?, ?)",
                       (recording.name, recorded_at.isoformat(), str(target), target.stat().st_size))
            saved += 1
        db.execute("INSERT OR REPLACE INTO processed (recording, processed_at) VALUES (?, ?)",
                   (recording.name, now.isoformat()))
    if not args.dry_run:
        prune(args.archive, db, max(1, args.keep_days), now)
    db.commit()
    db.close()
    print(json.dumps({"active": True, "mode": "collection-only", "archived": saved, "outside_survey_window": skipped, "as_of": now.isoformat()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

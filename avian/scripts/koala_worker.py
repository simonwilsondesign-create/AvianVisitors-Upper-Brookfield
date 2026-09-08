#!/usr/bin/env python3
"""Run the official koala recogniser over finished BirdNET recordings."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Australia/Brisbane")
KOALA_NAME = "Koala_CNN_LG_071223"


def recording_time(path: Path) -> dt.datetime:
    stamp = path.name.removesuffix(".wav").removeprefix("birdnet-")
    if "-birdnet-" in path.name:
        stamp = path.name.split("-birdnet-", 1)[0] + " " + path.name.split("-birdnet-", 1)[1].removesuffix(".wav")
    return dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)


def contains_koala(value: object) -> bool:
    if isinstance(value, str):
        return "koala" in value.lower()
    if isinstance(value, dict):
        return any(contains_koala(key) or contains_koala(item) for key, item in value.items())
    if isinstance(value, list):
        return any(contains_koala(item) for item in value)
    return False


def recogniser_score(filter_file: Path) -> float | None:
    """Return the supplied filter's true-positive rate as a display score."""
    try:
        data = json.loads(filter_file.read_text())
        tpr = data["Filters"][0]["TPR, FPR"][0]
        return max(0.0, min(1.0, float(tpr) / 100.0))
    except (OSError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return None


def initialise(db: sqlite3.Connection) -> None:
    db.execute("CREATE TABLE IF NOT EXISTS processed (recording TEXT PRIMARY KEY, processed_at TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS detections (detected_at TEXT NOT NULL, confidence REAL, recording TEXT NOT NULL UNIQUE, status TEXT NOT NULL)")
    db.commit()


def preserve_candidate_recording(recording: Path, destination: Path) -> None:
    """Keep candidate audio after BirdNET rotates StreamData recordings."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / recording.name
    if target.is_file():
        return
    temporary = destination / f".{recording.name}.tmp"
    shutil.copy2(recording, temporary)
    os.replace(temporary, target)


def process(recording: Path, args: argparse.Namespace, db: sqlite3.Connection) -> bool:
    if db.execute("SELECT 1 FROM processed WHERE recording = ?", (recording.name,)).fetchone():
        return False
    with tempfile.TemporaryDirectory(dir=args.work_dir, prefix="run-") as temporary:
        job = Path(temporary)
        input_file = job / recording.name
        shutil.copy2(recording, input_file)
        command = [args.python, args.avianz, "-c", "-b", "-d", str(job), "-r", KOALA_NAME]
        result = subprocess.run(command, input="y\n", text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env={**os.environ, "HOME": args.home}, timeout=120)
        if result.returncode:
            print(result.stdout[-4000:], file=sys.stderr)
            raise RuntimeError(f"AviaNZ failed for {recording.name}")
        data_file = Path(f"{input_file}.data")
        annotations = json.loads(data_file.read_text()) if data_file.exists() else []
        if contains_koala(annotations):
            # Keep the exact WAV AviaNZ just analysed before the temporary
            # directory is removed or BirdNET rotates StreamData.
            preserve_candidate_recording(input_file, args.candidate_recordings)
    db.execute("INSERT INTO processed (recording, processed_at) VALUES (?, ?)", (recording.name, dt.datetime.now(TZ).isoformat()))
    if contains_koala(annotations):
        detected = recording_time(recording).isoformat()
        db.execute("INSERT OR IGNORE INTO detections (detected_at, confidence, recording, status) VALUES (?, ?, ?, ?)", (detected, args.score, recording.name, "unreviewed"))
        print(f"koala candidate: {recording.name}")
    db.commit()
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/etc/birdnet/birdnet.conf")
    parser.add_argument("--recordings", default="/home/pi/BirdSongs/StreamData")
    parser.add_argument("--state", default="/var/lib/avian-koala/state.sqlite")
    parser.add_argument("--work-dir", default="/var/lib/avian-koala")
    parser.add_argument("--candidate-recordings", type=Path, default=Path("/var/lib/avian-koala/recordings"))
    parser.add_argument("--avianz", default="/opt/avian-koala/AviaNZ/AviaNZ.py")
    parser.add_argument("--python", default="/opt/avian-koala/venv/bin/python")
    parser.add_argument("--home", default="/home/pi")
    parser.add_argument("--filter", default="/home/pi/.avianz/Filters/Koala_CNN_LG_071223.txt")
    args = parser.parse_args()
    args.score = recogniser_score(Path(args.filter))
    # Analyse completed BirdNET recordings throughout the day.  The display
    # decides whether a candidate is recent or part of the dawn carry-over;
    # keeping the worker continuous also ensures daytime recordings and older
    # unprocessed files are added without deleting historical state.
    now = dt.datetime.now(TZ)
    recordings = sorted(Path(args.recordings).glob("*.wav"), key=lambda file: file.stat().st_mtime)
    db = sqlite3.connect(args.state)
    initialise(db)
    if args.score is not None:
        db.execute("UPDATE detections SET confidence = ? WHERE confidence IS NULL", (args.score,))
        db.commit()
    completed = 0
    for recording in recordings:
        # BirdNET keeps updating a recording's mtime until it removes it, so
        # file age is not a useful completion signal. A one-megabyte WAV is a
        # stable, several-second snapshot that AviaNZ can analyse in isolation.
        if recording.stat().st_size < 1_000_000:
            continue
        completed += int(process(recording, args, db))
    db.close()
    print(json.dumps({"active": True, "processed": completed, "as_of": now.isoformat()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

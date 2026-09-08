#!/usr/bin/env python3
"""Run the official koala recogniser over finished BirdNET recordings."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
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


def sun_utc(day: dt.date, latitude: float, longitude: float, sunrise: bool) -> dt.datetime:
    # NOAA's public sunrise equation. Accuracy is comfortably within a minute
    # for the scheduling boundary, without another runtime dependency.
    n = day.timetuple().tm_yday
    lng_hour = longitude / 15.0
    t = n + ((6.0 - lng_hour) / 24.0 if sunrise else (18.0 - lng_hour) / 24.0)
    m = (0.9856 * t) - 3.289
    l = (m + 1.916 * math.sin(math.radians(m)) + 0.020 * math.sin(math.radians(2 * m)) + 282.634) % 360
    ra = math.degrees(math.atan(0.91764 * math.tan(math.radians(l)))) % 360
    ra += (math.floor(l / 90) * 90) - (math.floor(ra / 90) * 90)
    ra /= 15.0
    sin_dec = 0.39782 * math.sin(math.radians(l))
    cos_dec = math.cos(math.asin(sin_dec))
    cos_h = (math.cos(math.radians(90.833)) - sin_dec * math.sin(math.radians(latitude))) / (cos_dec * math.cos(math.radians(latitude)))
    if not -1 <= cos_h <= 1:
        raise ValueError("sun does not rise/set at this latitude today")
    h = (360 - math.degrees(math.acos(cos_h)) if sunrise else math.degrees(math.acos(cos_h))) / 15.0
    ut = (h + ra - (0.06571 * t) - 6.622 - lng_hour) % 24
    result = dt.datetime.combine(day, dt.time(), dt.timezone.utc) + dt.timedelta(hours=ut)
    # The equation returns a UTC clock time. For easterly longitudes a local
    # sunrise can therefore land on the following local date unless its UTC
    # date is corrected back to the requested local calendar day.
    local_date = result.astimezone(TZ).date()
    if local_date > day:
        result -= dt.timedelta(days=1)
    elif local_date < day:
        result += dt.timedelta(days=1)
    return result


def listening_window(now: dt.datetime, latitude: float, longitude: float) -> tuple[dt.datetime, dt.datetime]:
    today = now.date()
    sunrise_today = sun_utc(today, latitude, longitude, True).astimezone(TZ)
    if now < sunrise_today:
        sunset = sun_utc(today - dt.timedelta(days=1), latitude, longitude, False).astimezone(TZ)
        return sunset + dt.timedelta(hours=1), sunrise_today
    sunset = sun_utc(today, latitude, longitude, False).astimezone(TZ)
    sunrise_tomorrow = sun_utc(today + dt.timedelta(days=1), latitude, longitude, True).astimezone(TZ)
    return sunset + dt.timedelta(hours=1), sunrise_tomorrow


def config_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(errors="replace").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


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
    parser.add_argument("--avianz", default="/opt/avian-koala/AviaNZ/AviaNZ.py")
    parser.add_argument("--python", default="/opt/avian-koala/venv/bin/python")
    parser.add_argument("--home", default="/home/pi")
    parser.add_argument("--filter", default="/home/pi/.avianz/Filters/Koala_CNN_LG_071223.txt")
    args = parser.parse_args()
    args.score = recogniser_score(Path(args.filter))
    values = config_values(Path(args.config))
    latitude, longitude = float(values.get("LATITUDE", "-27.4704")), float(values.get("LONGITUDE", "153.026"))
    now = dt.datetime.now(TZ)
    start, end = listening_window(now, latitude, longitude)
    if not start <= now < end:
        print(json.dumps({"active": False, "next_start": start.isoformat()}))
        return 0
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
    print(json.dumps({"active": True, "window_end": end.isoformat(), "processed": completed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

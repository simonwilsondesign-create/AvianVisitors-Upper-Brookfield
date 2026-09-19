#!/usr/bin/env python3
"""Create 30-second koala review candidates from BirdNET audio."""
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
import wave
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Australia/Brisbane")
KOALA_NAME = "Koala_CNN_LG_071223"


def recording_time(path: Path) -> dt.datetime:
    stamp = path.name.removesuffix(".wav")
    if "-birdnet-" in stamp:
        stamp = stamp.split("-birdnet-", 1)[0] + " " + stamp.split("-birdnet-", 1)[1]
    return dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)


def annotation_has_koala_event(value: object) -> bool:
    """Accept only an annotation with a koala label and a time interval.

    The AviaNZ filter name is present in every result file, including files
    without calls. A bare species/filter string must never create a candidate.
    """
    if isinstance(value, dict):
        label = " ".join(str(v) for k, v in value.items()
                         if k.lower() in {"label", "species", "calltype", "name", "type"})
        values = [v for k, v in value.items()
                  if k.lower() in {"start", "end", "starttime", "endtime", "offset", "duration"}
                  and isinstance(v, (int, float))]
        return ("koala" in label.lower() and len(values) >= 2) or any(annotation_has_koala_event(v) for v in value.values())
    if isinstance(value, list):
        if sum(isinstance(v, (int, float)) for v in value) >= 2 and annotation_has_koala_label(value):
            return True
        return any(annotation_has_koala_event(v) for v in value)
    return False


def annotation_has_koala_label(value: object) -> bool:
    """Find a koala species/call label within one AviaNZ annotation."""
    if isinstance(value, dict):
        if any("koala" in str(v).lower() for k, v in value.items()
               if k.lower() in {"label", "species", "calltype", "name", "type"}):
            return True
        return any(annotation_has_koala_label(v) for v in value.values())
    if isinstance(value, list):
        return any(annotation_has_koala_label(v) for v in value)
    return isinstance(value, str) and "koala" in value.lower()


def initialise(db: sqlite3.Connection) -> None:
    db.execute("CREATE TABLE IF NOT EXISTS processed (recording TEXT PRIMARY KEY, processed_at TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS detections (detected_at TEXT NOT NULL, confidence REAL, recording TEXT NOT NULL UNIQUE, status TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS worker_meta (name TEXT PRIMARY KEY, value TEXT NOT NULL)")
    # Previous records came from the metadata bug. Keep them for audit, but
    # they cannot be shown or mixed with newly generated review candidates.
    migrated = db.execute("SELECT 1 FROM worker_meta WHERE name = 'metadata_fix_v1'").fetchone()
    if not migrated:
        db.execute("UPDATE detections SET status = 'legacy-unverified' WHERE status = 'unreviewed'")
        db.execute("INSERT INTO worker_meta (name, value) VALUES ('metadata_fix_v1', 'done')")
    db.commit()


def wave_duration(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as source:
            return source.getnframes() / source.getframerate()
    except (wave.Error, OSError, ZeroDivisionError):
        return None


def combine_pair(first: Path, second: Path, output: Path) -> bool:
    try:
        with wave.open(str(first), "rb") as left, wave.open(str(second), "rb") as right:
            if left.getparams()[:3] != right.getparams()[:3]:
                return False
            with wave.open(str(output), "wb") as merged:
                merged.setparams(left.getparams())
                merged.writeframes(left.readframes(left.getnframes()))
                merged.writeframes(right.readframes(right.getnframes()))
        return True
    except (wave.Error, OSError):
        return False


def preserve_candidate_recording(recording: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / recording.name
    if not target.is_file():
        temporary = destination / f".{recording.name}.tmp"
        shutil.copy2(recording, temporary)
        os.replace(temporary, target)


def stage_recording(recording: Path, pending: Path) -> None:
    """Keep each finished 15-second recording until its neighbour arrives."""
    pending.mkdir(parents=True, exist_ok=True)
    target = pending / recording.name
    if not target.is_file():
        temporary = pending / f".{recording.name}.tmp"
        shutil.copy2(recording, temporary)
        os.replace(temporary, target)


def process(first: Path, second: Path, args: argparse.Namespace, db: sqlite3.Connection) -> bool:
    key = f"{first.name}|{second.name}"
    if db.execute("SELECT 1 FROM processed WHERE recording = ?", (key,)).fetchone():
        return False
    output_name = first.name.removesuffix(".wav") + "-koala-window.wav"
    with tempfile.TemporaryDirectory(dir=args.work_dir, prefix="run-") as temporary:
        job = Path(temporary)
        input_file = job / output_name
        if not combine_pair(first, second, input_file):
            return False
        command = [args.python, args.avianz, "-c", "-b", "-d", str(job), "-r", KOALA_NAME]
        result = subprocess.run(command, input="y\n", text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                env={**os.environ, "HOME": args.home}, timeout=120)
        if result.returncode:
            print(result.stdout[-4000:], file=sys.stderr)
            raise RuntimeError(f"AviaNZ failed for {key}")
        data_file = Path(f"{input_file}.data")
        annotations = json.loads(data_file.read_text()) if data_file.exists() else []
        detected = annotation_has_koala_event(annotations)
        # Keep one small, privacy-local diagnostic record. This makes a known
        # playback test inspectable without retaining every non-candidate WAV.
        diagnostic = Path(args.work_dir) / "last-avianz-result.json"
        diagnostic.write_text(json.dumps({
            "recording": output_name,
            "analysed_at": dt.datetime.now(TZ).isoformat(),
            "event_detected": detected,
            "annotations": annotations,
        }))
        if detected:
            preserve_candidate_recording(input_file, args.candidate_recordings)
    db.execute("INSERT INTO processed (recording, processed_at) VALUES (?, ?)", (key, dt.datetime.now(TZ).isoformat()))
    if detected:
        db.execute("INSERT OR IGNORE INTO detections (detected_at, confidence, recording, status) VALUES (?, NULL, ?, 'unreviewed')",
                   (recording_time(first).isoformat(), output_name))
        print(f"koala review candidate: {output_name}")
    db.commit()
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recordings", default="/home/pi/BirdSongs/StreamData")
    parser.add_argument("--state", default="/var/lib/avian-koala/state.sqlite")
    parser.add_argument("--work-dir", default="/var/lib/avian-koala")
    parser.add_argument("--candidate-recordings", type=Path, default=Path("/var/lib/avian-koala/recordings"))
    parser.add_argument("--pending", type=Path, default=Path("/var/lib/avian-koala/pending"))
    parser.add_argument("--avianz", default="/opt/avian-koala/AviaNZ/AviaNZ.py")
    parser.add_argument("--python", default="/opt/avian-koala/venv/bin/python")
    parser.add_argument("--home", default="/home/pi")
    args = parser.parse_args()
    now = dt.datetime.now(TZ)
    db = sqlite3.connect(args.state)
    initialise(db)
    # BirdNET rotates StreamData quickly, retaining only one completed clip.
    # Stage each valid clip first, then merge consecutive pairs on later polls.
    for recording in Path(args.recordings).glob("*.wav"):
        seconds = wave_duration(recording)
        if seconds is not None and seconds >= 14.9:
            stage_recording(recording, args.pending)
    recordings = sorted(args.pending.glob("*.wav"), key=recording_time)
    completed = 0
    for first, second in zip(recordings[::2], recordings[1::2]):
        when = recording_time(first)
        if (recording_time(second) - when).total_seconds() != 15:
            continue
        first_seconds, second_seconds = wave_duration(first), wave_duration(second)
        if first_seconds is None or second_seconds is None or first_seconds < 14.9 or second_seconds < 14.9:
            continue
        if process(first, second, args, db):
            first.unlink(missing_ok=True)
            second.unlink(missing_ok=True)
            completed += 1
    db.close()
    print(json.dumps({"active": True, "processed": completed, "as_of": now.isoformat()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

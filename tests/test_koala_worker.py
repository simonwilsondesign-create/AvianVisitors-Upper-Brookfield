import argparse
import json
import sqlite3
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from avian.scripts import koala_worker


def write_wav(path):
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, 8000, 120000, "NONE", "not compressed"))
        output.writeframes(b"\0\0" * 120000)


class TestKoalaWorker(unittest.TestCase):
    def test_filter_metadata_is_not_an_event(self):
        self.assertFalse(koala_worker.annotation_has_koala_event({"species": "Koala"}))
        self.assertFalse(koala_worker.annotation_has_koala_event(["Koala_CNN_LG_071223"]))
        self.assertTrue(koala_worker.annotation_has_koala_event({"label": "Koala", "start": 2.1, "end": 4.6}))

    def test_event_creates_a_30_second_unreviewed_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); first = root / "2026-09-07-birdnet-02:14:00.wav"; second = root / "2026-09-07-birdnet-02:14:15.wav"
            write_wav(first); write_wav(second); work = root / "work"; work.mkdir()
            args = argparse.Namespace(work_dir=str(work), candidate_recordings=root / "candidates", python="python", avianz="AviaNZ.py", home=str(root))
            db = sqlite3.connect(":memory:"); koala_worker.initialise(db)
            def recognise(command, **kwargs):
                copied = next(Path(command[command.index("-d") + 1]).glob("*.wav"))
                Path(f"{copied}.data").write_text(json.dumps({"label": "Koala", "start": 2.1, "end": 4.6}))
                return argparse.Namespace(returncode=0, stdout="ok")
            with patch.object(koala_worker.subprocess, "run", side_effect=recognise):
                self.assertTrue(koala_worker.process(first, second, args, db))
            row = db.execute("SELECT confidence, recording, status FROM detections").fetchone()
            self.assertEqual((row[0], row[2]), (None, "unreviewed"))
            with wave.open(str(root / "candidates" / row[1])) as candidate:
                self.assertEqual(candidate.getnframes(), 240000)

    def test_listening_window_is_dusk_to_dawn(self):
        self.assertTrue(koala_worker.is_listening_time(koala_worker.recording_time(Path("2026-09-07-birdnet-18:00:00.wav"))))
        self.assertFalse(koala_worker.is_listening_time(koala_worker.recording_time(Path("2026-09-07-birdnet-12:00:00.wav"))))

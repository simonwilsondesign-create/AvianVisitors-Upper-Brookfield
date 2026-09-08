import argparse
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from avian.scripts import koala_worker


class TestKoalaWorker(unittest.TestCase):
    def make_args(self, root: Path) -> argparse.Namespace:
        work = root / "work"
        work.mkdir()
        return argparse.Namespace(
            work_dir=str(work),
            candidate_recordings=str(root / "candidates"),
            python="python",
            avianz="AviaNZ.py",
            home=str(root),
            score=0.93,
        )

    def test_candidate_snapshot_survives_source_rotation_and_string_paths(self):
        """The recogniser gets a private copy and durable candidates outlive it."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "2026-09-07-birdnet-02:14:00.wav"
            payload = b"koala audio" * 128
            source.write_bytes(payload)
            args = self.make_args(root)
            db = sqlite3.connect(":memory:")
            koala_worker.initialise(db)

            def recognise(command, **_kwargs):
                copied = next(Path(command[command.index("-d") + 1]).glob("*.wav"))
                Path(f"{copied}.data").write_text(json.dumps({"species": "Koala"}))
                # Simulate BirdNET rotating the original while AviaNZ runs.
                source.unlink()
                return argparse.Namespace(returncode=0, stdout="ok")

            with patch.object(koala_worker.subprocess, "run", side_effect=recognise):
                self.assertTrue(koala_worker.process(source, args, db))

            snapshot = root / "candidates" / source.name
            self.assertEqual(snapshot.read_bytes(), payload)
            row = db.execute("SELECT detected_at, confidence, recording, status FROM detections").fetchone()
            self.assertEqual(row[0], "2026-09-07T02:14:00+10:00")
            self.assertEqual(row[1:], (0.93, source.name, "unreviewed"))
            # The processed record means a restart does not need the rotated file.
            self.assertFalse(koala_worker.process(source, args, db))
            db.close()

    def test_main_processes_a_daytime_completed_recording(self):
        """Continuous mode must not skip recordings solely because it is daytime."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            recordings = root / "recordings"
            recordings.mkdir()
            source = recordings / "2026-09-07-birdnet-13:24:00.wav"
            source.write_bytes(b"x" * 1_000_000)
            state = root / "state.sqlite"
            work = root / "work"
            work.mkdir()

            def recognise(command, **_kwargs):
                copied = next(Path(command[command.index("-d") + 1]).glob("*.wav"))
                Path(f"{copied}.data").write_text("[]")
                return argparse.Namespace(returncode=0, stdout="ok")

            argv = [
                "koala_worker.py", "--recordings", str(recordings), "--state", str(state),
                "--work-dir", str(work), "--candidate-recordings", str(root / "candidates"),
                "--filter", str(root / "missing-filter.json"),
            ]
            with patch("sys.argv", argv), patch.object(koala_worker.subprocess, "run", side_effect=recognise):
                self.assertEqual(koala_worker.main(), 0)

            db = sqlite3.connect(state)
            self.assertEqual(db.execute("SELECT recording FROM processed").fetchone()[0], source.name)
            db.close()


if __name__ == "__main__":
    unittest.main()

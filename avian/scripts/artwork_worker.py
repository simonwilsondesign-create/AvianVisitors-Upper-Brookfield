#!/usr/bin/env python3
"""Durable, single-process weekly artwork inventory and release worker.

It never calls an image provider unless ``--generate`` is explicitly supplied.
The default service invocation inventories all history, retains unresolved work
in SQLite, and records a resumable run result.
"""
from __future__ import annotations
import argparse, fcntl, json, os, shutil, sqlite3, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARIES = {"standard":"brisbane", "fun":"brisbane-weekend", "wes":"brisbane-wes-anderson"}
POSE_NAMES = {"1":"perched", "2":"flight"}  # storybook deliberately uses portrait/profile prompt files.

SCHEMA = """create table if not exists jobs (
 scientific text not null, library text not null, pose text not null, common text,
 first_seen text not null, last_seen text, detections integer default 0, best_confidence real default 0,
 status text not null default 'pending', attempts integer not null default 0, next_retry text,
 last_error text, updated_at text not null, primary key(scientific, library, pose));
create table if not exists runs (id integer primary key, started_at text, finished_at text, status text, detail text);
create table if not exists checkpoints (name text primary key, value text not null);"""

def now() -> str: return datetime.now(timezone.utc).isoformat(timespec="seconds")
def db_open(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True); db = sqlite3.connect(path); db.executescript(SCHEMA); return db
def run_report(api: str, output: Path) -> dict:
    command = [sys.executable, str(ROOT / "scripts" / "report_missing_illustrations.py"), "--api", api, "--hours", "1000000", "--json-output", str(output)]
    subprocess.run(command, check=True, timeout=90)
    data = json.loads(output.read_text())
    if not isinstance(data.get("species"), list): raise RuntimeError("strict inventory output missing species")
    return data
def enqueue(db: sqlite3.Connection, inventory: dict, min_detections: int, min_confidence: float) -> int:
    count = 0; stamp = now()
    for species in inventory["species"]:
        for library, poses in species["missing"].items():
            if library not in LIBRARIES: raise RuntimeError(f"unknown library {library}")
            for missing_part in poses:
                pose = "2" if str(missing_part).endswith("-2.png") else "1"
                if pose not in POSE_NAMES: raise RuntimeError(f"unknown pose {pose}")
                status = 'pending' if int(species.get('detections', 0)) >= min_detections and float(species.get('best_confidence', 0)) >= min_confidence else 'needs review'
                db.execute("""insert into jobs(scientific,library,pose,common,first_seen,last_seen,detections,best_confidence,status,updated_at)
                  values(?,?,?,?,?,?,?,?, ?,?) on conflict(scientific,library,pose) do update set
                  common=excluded.common,last_seen=excluded.last_seen,detections=max(jobs.detections,excluded.detections),
                  best_confidence=max(jobs.best_confidence,excluded.best_confidence),status=case when jobs.status in ('published','needs review') then excluded.status else jobs.status end,updated_at=excluded.updated_at""",
                  (species["scientific"],library,pose,species.get("common",""),species.get("last_seen",""),species.get("last_seen",""),species.get("detections",0),species.get("best_confidence",0),status,stamp)); count += 1
    db.commit(); return count
def eligible(db: sqlite3.Connection, limit: int) -> list[tuple]:
    return db.execute("select scientific,library,pose,common,attempts from jobs where status in ('pending','retryable failure') and (next_retry is null or next_retry <= ?) order by first_seen,scientific,library,pose limit ?", (now(), limit)).fetchall()
def command_for(job: tuple, prompt_dir: Path) -> list[str]:
    scientific, library, pose, common, _attempts = job
    # The existing curated style-specific batches are authoritative. The worker
    # only selects a one-pose record; it never turns story portrait/profile into
    # standard perched/flight semantics.
    prompt = prompt_dir / f"missing-{library}-prompts.jsonl"
    if not prompt.is_file(): raise RuntimeError(f"missing approved prompt batch {prompt}")
    return ["# selected", scientific, library, pose, common]
def process(db: sqlite3.Connection, jobs: list[tuple], generate: bool, prompt_dir: Path) -> None:
    for job in jobs:
        scientific, library, pose, _common, attempts = job
        if not generate: continue
        try:
            command_for(job, prompt_dir)
            # Provider submission intentionally lives behind a separately reviewed
            # invocation. This durable worker marks it generating only after the
            # real generator has been wired with an explicit output path.
            raise RuntimeError("generation adapter is not configured")
        except Exception as error:
            retry_hours = min(24 * 14, 2 ** min(attempts + 1, 10))
            db.execute("update jobs set status='retryable failure',attempts=attempts+1,next_retry=datetime('now', ?),last_error=?,updated_at=? where scientific=? and library=? and pose=?", (f"+{retry_hours} hours", str(error)[:1000], now(),scientific,library,pose))
    db.commit()
def main() -> int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--api",default="http://birdnet.local/avian/api/birdnet-api.php")
    p.add_argument("--state",type=Path,default=Path("/var/lib/avian-artwork/state.sqlite")); p.add_argument("--work-dir",type=Path,default=Path("/var/lib/avian-artwork")); p.add_argument("--limit",type=int,default=12); p.add_argument("--generate",action="store_true"); p.add_argument("--prompt-dir",type=Path,default=ROOT.parent / "_Brief Files"); p.add_argument("--min-detections",type=int,default=20); p.add_argument("--min-confidence",type=float,default=.90)
    args=p.parse_args();
    if args.limit < 1: p.error("--limit must be positive")
    args.work_dir.mkdir(parents=True, exist_ok=True)
    with (args.work_dir / "worker.lock").open("w") as lock:
      try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
      except BlockingIOError: print("artwork worker already running",file=sys.stderr); return 0
      db=db_open(args.state); started=now(); run_id=db.execute("insert into runs(started_at,status) values(?,?)",(started,"running")).lastrowid; db.commit()
      try:
        inventory=run_report(args.api,args.work_dir / "latest-inventory.json"); queued=enqueue(db,inventory,args.min_detections,args.min_confidence); jobs=eligible(db,args.limit); process(db,jobs,args.generate,args.prompt_dir)
        detail=json.dumps({"inventory_species":len(inventory["species"]),"queued_parts":queued,"eligible":len(jobs),"generation_enabled":args.generate}); db.execute("update runs set finished_at=?,status='ok',detail=? where id=?",(now(),detail,run_id)); db.commit(); print(detail); return 0
      except Exception as error:
        db.execute("update runs set finished_at=?,status='failed',detail=? where id=?",(now(),str(error),run_id)); db.commit(); print(f"error: {error}",file=sys.stderr); return 1
if __name__ == "__main__": raise SystemExit(main())

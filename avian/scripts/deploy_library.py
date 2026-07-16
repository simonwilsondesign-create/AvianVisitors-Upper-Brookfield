#!/usr/bin/env python3
"""Safely deploy one approved illustration library into the runtime folder.

Example:
    python3 avian/scripts/deploy_library.py brisbane --dry-run
    python3 avian/scripts/deploy_library.py brisbane
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def fail(message: str) -> None:
    raise RuntimeError(message)


def validate_cutouts(cutouts: Path) -> list[Path]:
    """Return valid source files, rejecting unsafe or incomplete libraries."""
    if not cutouts.is_dir():
        fail(f"cutout directory does not exist: {cutouts}")
    files = sorted(cutouts.glob("*.png"))
    if not files:
        fail(f"no PNG files found in {cutouts}")

    from PIL import Image

    stems: set[str] = set()
    bases: dict[str, set[str]] = {}
    for path in files:
        if not SLUG.fullmatch(path.stem):
            fail(f"invalid illustration filename: {path.name}")
        if path.stem in stems:
            fail(f"duplicate illustration filename: {path.name}")
        stems.add(path.stem)
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                if "A" not in image.getbands():
                    fail(f"cutout has no alpha channel: {path.name}")
        except (OSError, SyntaxError) as error:
            fail(f"invalid PNG {path}: {error}")
        base = path.stem[:-2] if path.stem.endswith("-2") else path.stem
        bases.setdefault(base, set()).add(path.stem)

    incomplete = sorted(base for base, names in bases.items()
                        if {base, f"{base}-2"} != names)
    if incomplete:
        fail("missing pose pair(s): " + ", ".join(incomplete))
    return files


def validate_metadata(frontend: Path, files: list[Path]) -> None:
    expected = {path.stem for path in files}
    for name in ("dims.json", "masks.json"):
        try:
            actual = set(json.loads((frontend / name).read_text()))
        except (OSError, json.JSONDecodeError) as error:
            fail(f"could not read generated {name}: {error}")
        if actual != expected:
            missing, extra = sorted(expected - actual), sorted(actual - expected)
            fail(f"{name} does not match installed files; missing={missing}, extra={extra}")


def build_metadata(script: Path, illustrations: Path, output: Path, files: list[Path]) -> None:
    output.mkdir(parents=True)
    result = subprocess.run(
        [sys.executable, str(script), "--illustrations", str(illustrations), "--frontend", str(output)],
        text=True, capture_output=True,
    )
    if result.returncode:
        fail("mask generation failed:\n" + (result.stderr or result.stdout))
    print(result.stdout.strip())
    validate_metadata(output, files)


def deploy(library: str, dry_run: bool) -> int:
    root = Path(__file__).resolve().parents[1]
    cutouts = root / "assets" / "illustration-libraries" / library / "cutouts"
    files = validate_cutouts(cutouts)
    species = len(files) // 2
    print(f"library '{library}': {species} species, {len(files)} PNG cutouts")

    with tempfile.TemporaryDirectory(prefix="deploy-library-", dir=root / "assets") as temporary:
        temporary_path = Path(temporary)
        staged_illustrations = temporary_path / "illustrations"
        shutil.copytree(cutouts, staged_illustrations)
        staged_frontend = temporary_path / "frontend"
        build_metadata(root / "scripts" / "build_masks.py", staged_illustrations, staged_frontend, files)
        if dry_run:
            print("dry run successful; active illustrations and metadata were not changed")
            return 0

        active = root / "assets" / "illustrations"
        frontend = root / "frontend"
        backups = root / "assets" / "illustrations-backups"
        backups.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = backups / f"{stamp}-{library}"
        old_dims, old_masks = frontend / "dims.json", frontend / "masks.json"
        backup.mkdir()

        # All failure-prone work happened above. Keep originals until every
        # replacement is in place, then retain them in the dated backup.
        try:
            if active.exists():
                active.rename(backup / "illustrations")
            staged_illustrations.rename(active)
            shutil.copy2(old_dims, backup / "dims.json")
            shutil.copy2(old_masks, backup / "masks.json")
            shutil.copy2(staged_frontend / "dims.json", old_dims)
            shutil.copy2(staged_frontend / "masks.json", old_masks)
            validate_metadata(frontend, files)
        except Exception:
            if (backup / "illustrations").exists():
                if active.exists():
                    shutil.rmtree(active)
                (backup / "illustrations").rename(active)
            if (backup / "dims.json").exists():
                shutil.copy2(backup / "dims.json", old_dims)
            if (backup / "masks.json").exists():
                shutil.copy2(backup / "masks.json", old_masks)
            raise
        print(f"deployed {len(files)} files to {active}; backup retained at {backup}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", help="library name under avian/assets/illustration-libraries/")
    parser.add_argument("--dry-run", action="store_true", help="validate and build masks without changing runtime files")
    args = parser.parse_args()
    try:
        return deploy(args.library, args.dry_run)
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

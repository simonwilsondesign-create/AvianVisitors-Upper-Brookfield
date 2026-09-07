#!/usr/bin/env python3
"""Merge approved generated PNGs into a complete, publishable art library.

This deliberately does not generate or identify birds.  It is the handoff
between a reviewed external image-generation run and the atomic publisher.
Existing approved cutouts are copied first, then only named incoming PNGs are
allowed to replace matching files in the new staging directory.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIBRARIES = {
    "standard": "brisbane",
    "fun": "brisbane-weekend",
    "wes": "brisbane-wes-anderson",
}
PNG_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\.png")


def validate_png(path: Path) -> None:
    from PIL import Image

    with Image.open(path) as image:
        image.load()
        if image.format != "PNG" or image.width < 9 or image.height < 9:
            raise RuntimeError(f"invalid PNG: {path.name}")
        if "A" not in image.getbands() or image.getchannel("A").getbbox() is None:
            raise RuntimeError(
                f"{path.name} needs a non-empty transparent alpha channel; "
                "run cutout.py first if the generator returned white background"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", choices=LIBRARIES)
    parser.add_argument("--incoming", type=Path, required=True,
                        help="reviewed transparent PNGs from the generator")
    parser.add_argument("--output", type=Path, required=True,
                        help="new, empty staging directory")
    args = parser.parse_args()

    incoming = args.incoming.resolve()
    output = args.output.resolve()
    base = ROOT / "assets" / "illustration-libraries" / LIBRARIES[args.library] / "cutouts"
    if not incoming.is_dir():
        parser.error(f"incoming directory does not exist: {incoming}")
    if output.exists() and any(output.iterdir()):
        parser.error(f"output must be new or empty: {output}")

    files = sorted(incoming.glob("*.png"))
    if not files:
        parser.error("incoming directory has no PNG files")
    unsafe = [path.name for path in files if not PNG_NAME.fullmatch(path.name)]
    if unsafe:
        parser.error("unsafe filenames: " + ", ".join(unsafe))
    for path in files:
        validate_png(path)

    output.mkdir(parents=True, exist_ok=True)
    for old in base.glob("*.png"):
        shutil.copy2(old, output / old.name)
    for new in files:
        shutil.copy2(new, output / new.name)

    manifest = {
        "schema": 1,
        "library": args.library,
        "prepared_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base": str(base),
        "imported": [path.name for path in files],
    }
    (output / "import-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"staging": str(output), "imported": len(files), "files": len(list(output.glob('*.png')))}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)

#!/usr/bin/env python3
"""Merge the supported Upper Brookfield birds into BirdNET's whitelist."""

from __future__ import annotations

import argparse
import os
import re
import tempfile
from pathlib import Path

LABEL = re.compile(r"^[A-Z][A-Za-z-]+ [a-z][a-z-]+(?: [a-z][a-z-]+)?_.+$")


def scientific_name(line: str) -> str:
    return line.split("_", 1)[0]


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def merge(source: Path, target: Path) -> tuple[int, int]:
    required = read_lines(source)
    invalid = [line for line in required if not LABEL.fullmatch(line)]
    if invalid:
        raise ValueError(f"invalid whitelist label(s): {', '.join(invalid)}")

    existing = read_lines(target)
    names = {scientific_name(line) for line in existing}
    additions = [line for line in required if scientific_name(line) not in names]
    merged = existing + additions

    target.parent.mkdir(parents=True, exist_ok=True)
    mode = target.stat().st_mode if target.exists() else 0o664
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=target.parent, delete=False
    ) as handle:
        handle.write("\n".join(merged) + "\n")
        temporary = Path(handle.name)
    os.chmod(temporary, mode)
    os.replace(temporary, target)
    return len(additions), len(merged)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).with_name("upper-brookfield-birdnet-whitelist.txt"),
    )
    parser.add_argument("--target", type=Path, default=root / "whitelist_species_list.txt")
    args = parser.parse_args()
    added, total = merge(args.source, args.target)
    print(f"Upper Brookfield whitelist: added {added}; {total} total entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

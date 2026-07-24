#!/usr/bin/env python3
"""Report detected species that do not yet have complete illustration sets.

The report compares BirdNET-Pi's recent API response with the paired PNGs in
the standard, fun and Wes Anderson libraries. It prints a prompt-ready
``Scientific name|Common name`` list as well as the required filenames.

Examples:
    python3 avian/scripts/report_missing_illustrations.py
    python3 avian/scripts/report_missing_illustrations.py --hours 1000000
    python3 avian/scripts/report_missing_illustrations.py --output missing.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


LIBRARIES = {
    "standard": "brisbane",
    "fun": "brisbane-weekend",
    "wes": "brisbane-wes-anderson",
}


def slugify(scientific_name: str) -> str:
    """Match the filename conversion used by avian/api/cutout.php."""
    return re.sub(r"[^a-z0-9]+", "-", scientific_name.lower()).strip("-")


def fetch_recent(api_url: str, hours: int) -> dict:
    separator = "&" if "?" in api_url else "?"
    url = api_url + separator + urlencode({"action": "recent", "hours": hours})
    try:
        with urlopen(url, timeout=15) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(f"could not read BirdNET-Pi API at {url}: {error}") from error


def find_missing(data: dict, assets: Path) -> list[dict]:
    missing_species: list[dict] = []
    for species in data.get("species", []):
        scientific = str(species.get("sci", "")).strip()
        common = str(species.get("com", "")).strip()
        if not scientific:
            continue
        stem = slugify(scientific)
        required = (f"{stem}.png", f"{stem}-2.png")
        missing_by_library: dict[str, list[str]] = {}
        for label, directory in LIBRARIES.items():
            cutouts = assets / directory / "cutouts"
            absent = [filename for filename in required if not (cutouts / filename).is_file()]
            if absent:
                missing_by_library[label] = absent
        if missing_by_library:
            missing_species.append(
                {
                    "scientific": scientific,
                    "common": common,
                    "stem": stem,
                    "detections": int(species.get("n", 0)),
                    "best_confidence": float(species.get("best_conf", 0)),
                    "last_seen": str(species.get("last_seen", "")),
                    "missing": missing_by_library,
                }
            )
    return sorted(missing_species, key=lambda item: (-item["detections"], item["scientific"]))


def markdown_report(missing: list[dict], hours: int, as_of: str) -> str:
    window = "all recorded history" if hours >= 1_000_000 else f"the last {hours} hours"
    png_count = sum(len(files) for item in missing for files in item["missing"].values())
    lines = [
        "# Missing bird illustrations",
        "",
        f"Detection window: {window}  ",
        f"BirdNET data as of: {as_of or 'unknown'}  ",
        f"Report generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        f"**{len(missing)} species need artwork; {png_count} PNG files are missing.**",
        "",
    ]
    if not missing:
        lines.append("Every detected species has both poses in all three libraries.")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "| Required filename stem | Scientific name | Common name | Detections | Best confidence | Last detected | Missing sets |",
            "|---|---|---|---:|---:|---|---|",
        ]
    )
    for item in missing:
        sets = ", ".join(item["missing"])
        confidence = f"{item['best_confidence']:.0%}"
        lines.append(
            f"| `{item['stem']}` | {item['scientific']} | {item['common']} | "
            f"{item['detections']} | {confidence} | {item['last_seen']} | {sets} |"
        )

    lines.extend(["", "## Batch source list", "", "```text"])
    lines.extend(f"{item['scientific']}|{item['common']}" for item in missing)
    lines.extend(["```", "", "## Required paired filenames", ""])
    for item in missing:
        lines.append(f"- `{item['stem']}.png` — perched or standing")
        lines.append(f"- `{item['stem']}-2.png` — in flight")
    lines.extend(
        [
            "",
            "Generate each pair in all three styles: standard, fun and Wes Anderson.",
            "Review low-confidence or single detections before commissioning artwork.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    avian_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api",
        default="http://birdnet.local/avian/api/birdnet-api.php",
        help="BirdNET-Pi API URL",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="rolling detection window; use 1000000 for all history (default: 24)",
    )
    parser.add_argument("--input", type=Path, help="read a saved recent-API JSON file instead")
    parser.add_argument("--output", type=Path, help="write Markdown here instead of stdout")
    args = parser.parse_args()

    if args.hours < 1:
        parser.error("--hours must be at least 1")

    try:
        data = json.loads(args.input.read_text()) if args.input else fetch_recent(args.api, args.hours)
        missing = find_missing(data, avian_root / "assets" / "illustration-libraries")
        report = markdown_report(missing, args.hours, str(data.get("as_of", "")))
    except (OSError, RuntimeError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report)
        print(f"wrote {len(missing)} missing species to {args.output}")
    else:
        print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
import subprocess
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


def validate_response(data: object) -> dict:
    """Reject API failures rather than accidentally treating them as no birds."""
    if not isinstance(data, dict):
        raise RuntimeError("BirdNET response must be an object")
    if data.get("error"):
        raise RuntimeError(f"BirdNET API error: {data['error']}")
    species = data.get("species")
    if not isinstance(species, list):
        raise RuntimeError("BirdNET response has no species array")
    for index, item in enumerate(species):
        if not isinstance(item, dict) or not str(item.get("sci", "")).strip():
            raise RuntimeError(f"invalid species entry at index {index}")
    return data


def fetch_recent(api_url: str, hours: int) -> dict:
    separator = "&" if "?" in api_url else "?"
    url = api_url + separator + urlencode({"action": "recent", "hours": hours})
    try:
        with urlopen(url, timeout=15) as response:
            return validate_response(json.load(response))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as python_error:
        # Python's resolver does not consistently send .local lookups through
        # Bonjour on macOS. curl does, so use it as a no-shell fallback.
        try:
            result = subprocess.run(
                ["curl", "-fsS", "--max-time", "15", url],
                check=True,
                capture_output=True,
                text=True,
            )
            return validate_response(json.loads(result.stdout))
        except (
            FileNotFoundError,
            subprocess.CalledProcessError,
            json.JSONDecodeError,
        ) as curl_error:
            raise RuntimeError(
                f"could not read BirdNET-Pi API at {url}; "
                f"Python: {python_error}; curl fallback: {curl_error}. "
                "If birdnet.local is unavailable, pass the Pi's numeric address "
                "with --api http://PI_ADDRESS/avian/api/birdnet-api.php"
            ) from curl_error


def valid_png(path: Path) -> bool:
    """A filename alone is not usable artwork: require readable nonempty alpha."""
    try:
        from PIL import Image
        with Image.open(path) as image:
            image.load()
            return (image.format == "PNG" and image.width > 8 and image.height > 8
                    and "A" in image.getbands() and image.getchannel("A").getbbox() is not None)
    except (OSError, ValueError):
        return False


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
            absent = [filename for filename in required if not valid_png(cutouts / filename)]
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
        default=1000000,
        help="rolling detection window; all recorded history by default",
    )
    parser.add_argument("--input", type=Path, help="read a saved recent-API JSON file instead")
    parser.add_argument("--output", type=Path, help="write Markdown here instead of stdout")
    parser.add_argument("--json-output", type=Path, help="write structured queue input JSON")
    args = parser.parse_args()

    if args.hours < 1:
        parser.error("--hours must be at least 1")

    try:
        data = validate_response(json.loads(args.input.read_text())) if args.input else fetch_recent(args.api, args.hours)
        missing = find_missing(data, avian_root / "assets" / "illustration-libraries")
        report = markdown_report(missing, args.hours, str(data.get("as_of", "")))
    except (OSError, RuntimeError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report)
        print(f"wrote {len(missing)} missing species to {args.output}")
    elif not args.json_output:
        print(report, end="")
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps({
            "schema": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
            "as_of": data.get("as_of"), "hours": args.hours, "species": missing,
        }, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

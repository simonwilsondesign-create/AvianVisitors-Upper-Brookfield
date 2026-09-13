#!/usr/bin/env bash
# Generate the complete missing-Brisbane illustration brief into a fresh,
# review-only library. It never changes the artwork used by the live site.
set -u -o pipefail

if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  echo "GEMINI_API_KEY is not set in this terminal." >&2
  exit 2
fi

repo="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo"

stamp="$(date +%Y%m%d-%H%M%S)"
run_root="${1:-_Brief Files/test-output/missing-brisbane-birds/$stamp}"
if [[ -e "$run_root" ]]; then
  echo "Refusing to reuse existing output: $run_root" >&2
  exit 2
fi
mkdir -p "$run_root"

status=0
run() {
  "$@" || status=1
}

echo "Output: $run_root"
echo "[1/6] Standard kacho-e illustrations (14 images)"
run python avian/scripts/pregen.py \
  --labels "_Brief Files/missing-bird-labels.txt" \
  --out "$run_root/standard" --sleep 6

echo "[2/6] Cutting standard backgrounds"
run python avian/scripts/cutout.py --dir "$run_root/standard"

echo "[3/6] Fun character illustrations (14 images)"
run python "_Brief Files/run_gemini_prompt_batch.py" \
  --manifest "_Brief Files/missing-fun-prompts.jsonl" \
  --limit-species 7 --out "$run_root/fun" --sleep 6

echo "[4/6] Cutting fun backgrounds"
run python avian/scripts/cutout.py --dir "$run_root/fun"

echo "[5/6] Wes storybook illustrations (14 images)"
run python "_Brief Files/run_gemini_prompt_batch.py" \
  --manifest "_Brief Files/missing-wes-prompts.jsonl" \
  --limit-species 7 --out "$run_root/wes" --sleep 6 --no-style-reference

echo "[6/6] Cutting Wes backgrounds"
run python avian/scripts/cutout.py --dir "$run_root/wes"

echo "Finished. Review the 42 transparent PNGs in: $run_root"
exit "$status"

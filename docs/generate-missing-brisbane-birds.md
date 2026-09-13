# Generate the missing Brisbane birds

This brief covers the seven species in
`_Brief Files/missing-bird-illustrations.md`: Eastern Yellow Robin, Spotted
Pardalote, Olive-backed Oriole, Silvereye, Black-faced Cuckooshrike,
White-throated Treecreeper, and Rose Robin. It makes 42 images: two poses in
each of the standard, fun, and Wes libraries.

The report was generated from all recorded history on 25 July 2026. Generate a
fresh report from the Pi before commissioning new artwork if the Pi is
available, since later detections may have added species.

## 1. Open Terminal and prepare Python

```sh
cd ~/Documents/AvianVisitors
python3 -m venv .venv-artwork
source .venv-artwork/bin/activate
python -m pip install --upgrade pip
python -m pip install Pillow rembg onnxruntime
```

## 2. Create a Gemini API key

Open [Google AI Studio](https://aistudio.google.com/) in a browser. Sign in to
your Google account there using your normal Google password and any two-factor
authentication. Do not enter that password in Terminal.

Choose **Get API key** (or **API keys**), create a key for a project, copy it,
then return to Terminal and run this command. It hides the key as you paste it
and does not put it in shell history:

```sh
read -rs 'GEMINI_API_KEY?Paste the Gemini API key, then press Return: '
export GEMINI_API_KEY
echo
```

If AI Studio asks for billing, complete that in the browser. The API key is a
secret: do not put it in a file, a prompt, a screenshot, or a Git commit.

## 3. Check the two supplied prompt batches

These commands do not call Gemini or create images. Each should say `14
prompts (7 species)`.

```sh
python "_Brief Files/run_gemini_prompt_batch.py" \
  --manifest "_Brief Files/missing-fun-prompts.jsonl" \
  --limit-species 7 --dry-run

python "_Brief Files/run_gemini_prompt_batch.py" \
  --manifest "_Brief Files/missing-wes-prompts.jsonl" \
  --limit-species 7 --dry-run --no-style-reference
```

The fun batch deliberately uses the included character-painting reference. The
Wes batch must use `--no-style-reference`: its own prompts contain the complete
storybook art direction, and should not inherit the fun character-painting
style.

## 4. Generate all three libraries

Make one new output folder. Do not reuse an existing folder name.

```sh
ARTWORK_RUN="_Brief Files/output/$(date +%Y%m%d-%H%M%S)-missing-birds"
mkdir -p "$ARTWORK_RUN"

# Standard Brisbane set: 14 images, two poses for each of the seven birds.
python avian/scripts/pregen.py \
  --labels "_Brief Files/missing-bird-labels.txt" \
  --out "$ARTWORK_RUN/standard" \
  --sleep 6

# Friday fun-character set: 14 images.
python "_Brief Files/run_gemini_prompt_batch.py" \
  --manifest "_Brief Files/missing-fun-prompts.jsonl" \
  --limit-species 7 \
  --out "$ARTWORK_RUN/fun" \
  --sleep 6

# Saturday/Sunday Wes storybook set: 14 images.
python "_Brief Files/run_gemini_prompt_batch.py" \
  --manifest "_Brief Files/missing-wes-prompts.jsonl" \
  --limit-species 7 \
  --out "$ARTWORK_RUN/wes" \
  --sleep 6 \
  --no-style-reference
```

## 5. Make transparent cutouts

This removes the flat backgrounds and crops each image. The first run downloads
the background-removal model, which is large.

```sh
python avian/scripts/cutout.py --dir "$ARTWORK_RUN/standard"
python avian/scripts/cutout.py --dir "$ARTWORK_RUN/fun"
python avian/scripts/cutout.py --dir "$ARTWORK_RUN/wes"
open "$ARTWORK_RUN"
```

Review every pair before publishing: species markings, complete feet and tails,
both flight wings, and clean transparent edges. Do not publish generated work
until it has been reviewed.

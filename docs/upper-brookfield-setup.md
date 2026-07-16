# Upper Brookfield AvianVisitors

This is the Upper Brookfield, Brisbane fork of AvianVisitors, prepared for a
future Raspberry Pi 5 installation. The runtime library is deliberately
limited to approved local bird cutouts; the original US set is retained only
as a non-runtime reference library.

## Artwork libraries

`avian/assets/illustration-libraries/brisbane/cutouts/` contains the approved
transparent PNGs. It is the source for runtime artwork.

`avian/assets/illustration-libraries/brisbane/generated/` contains the
cream-background generation inputs and stays local/ignored. Do not deploy it.

`avian/assets/illustration-libraries/original-us/` is retained for reference,
but must not be copied to `avian/assets/illustrations/`. The latter is the only
runtime artwork path. `avian/frontend/dims.json` and `masks.json` are generated
from that active directory and must be committed with it.

The Upper Brookfield source lists are in `avian/scripts/upper-brookfield-*.txt`.

## Deploy and validate locally

From the repository root:

```bash
python3 avian/scripts/deploy_library.py brisbane --dry-run
python3 avian/scripts/deploy_library.py brisbane
python3 avian/scripts/build_masks.py --check
```

The deploy command validates PNG readability, alpha channels, slug names and
perched/flight pose pairs before it changes anything. It builds metadata in a
temporary directory, checks it against the selected files, then swaps the
active directory and retains a dated backup under
`avian/assets/illustrations-backups/` (ignored by Git). Inspect the collage in
a browser after deployment, especially transparent edges and paired poses.

## Raspberry Pi installation and updates

Do not run the installer on macOS. On a Pi 5 with a supported 64-bit Raspberry
Pi OS and passwordless `sudo`, use the installer from this fork. It now clones
the `upper-brookfield` branch from this repository by default:

```bash
curl -s https://raw.githubusercontent.com/simonwilsondesign-create/AvianVisitors-Upper-Brookfield/upper-brookfield/newinstaller.sh | bash
```

After cloning/updating an existing Pi checkout, run the deploy command above
there if the active artwork or metadata needs refreshing. Confirm that `origin`
is this fork and retain the AvianVisitors source as `upstream`:

```bash
git -C ~/BirdNET-Pi remote -v
git -C ~/BirdNET-Pi remote add upstream https://github.com/Twarner491/AvianVisitors.git
git -C ~/BirdNET-Pi fetch upstream
git -C ~/BirdNET-Pi log --oneline HEAD..upstream/main
```

Only merge or rebase selected upstream changes after reviewing them on a branch;
do not run the normal updater against `upstream` without an explicit branch.
The updater defaults should remain `origin` and `upper-brookfield` on this fork.

BirdNET detection data is assumed to be managed beneath `~/BirdNET-Pi` (the
configuration defaults to `~/BirdNET-Pi/Extracted` and related dataset paths).
That exact Pi filesystem state has not been verified here: confirm
`/etc/birdnet/birdnet.conf`, `RECS_DIR`, `EXTRACTED`, and database locations on
the target Pi before migration or backup work.

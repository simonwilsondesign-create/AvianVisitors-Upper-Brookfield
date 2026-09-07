# Durable artwork pipeline

`report_missing_illustrations.py` strictly validates BirdNET's API response and
each source PNG's alpha bounds. It scans all history by default. A malformed
response fails the run; it can never clear the backlog.

`artwork_worker.py` persists jobs in `/var/lib/avian-artwork/state.sqlite`,
uses a non-blocking lock, retains unresolved parts, and records every run. The
installed service only inventories. It will not call a provider unless an
operator deliberately supplies `--generate`; generation adapter wiring and
provider credentials belong in `/etc/avian/artwork.env`, outside the web root.

Jobs are keyed by scientific name, library, and pose. Standard and fun use
perched/flight. The storybook prompt batch is authoritative for portrait/profile
semantics, so do not mechanically reuse a standard flight prompt. For the
initial review, select only confident species (suggested >=20 detections and
>=0.90 confidence), then explicitly admit credible exceptional records such as
an owl. Preserve approved images and generate only the missing pose.

After you generate and visually review an image batch, keep the approved PNGs
in a separate folder for each style. They must already have a real alpha
channel. If Google returned a flat white ground, remove it before importing:

```sh
python3 avian/scripts/cutout.py --dir /srv/avian/incoming/standard
```

Prepare a new full library without changing the active artwork:

```sh
python3 avian/scripts/prepare_artwork_release.py standard \
  --incoming /srv/avian/incoming/standard \
  --output /srv/avian/staging/standard-cutouts
```

Repeat for `fun` and `wes`. Then publish the tested complete library:

```sh
python3 avian/scripts/publish_artwork_release.py standard \
  --source /srv/avian/staging/standard-cutouts
```

The command validates PNGs, alpha bounds, pairs, dimensions/masks, writes a
manifest, and atomically replaces `assets/illustration-releases/<library>/CURRENT`.
It retains four releases. Roll back by atomically replacing `CURRENT` with the
name of an existing validated release; never point it at a partial directory.

Install scheduling on the Pi after creating the state directory for the
existing `birdnet` service account:

```sh
sudo install -d -o birdnet -g birdnet /var/lib/avian-artwork
sudo install -m 0644 avian/systemd/avian-artwork.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now avian-artwork.timer
```

The browser first reads `illustration-library.php`, pins its `revision`, and
must request both metadata and images with that revision. On a revision change,
fetch the new metadata before replacing the pinned image URLs. `cutout.php`
returns 409 for a stale requested revision, which tells the browser to reload
the library status rather than mix metadata and artwork.

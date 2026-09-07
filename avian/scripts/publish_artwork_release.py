#!/usr/bin/env python3
"""Validate a complete library and atomically make it the active release.

Input is a trusted, complete cutout directory. Use prepare_artwork_release.py
to merge reviewed new artwork with the active source library before publishing;
every published release is then whole and immutable.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SLUG=re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
def fail(m): raise RuntimeError(m)
def validate(directory: Path):
    from PIL import Image
    files=sorted(directory.glob("*.png")); seen=set()
    if not files: fail("no PNGs")
    for p in files:
      if not SLUG.fullmatch(p.stem) or p.stem in seen: fail(f"unsafe/duplicate filename {p.name}")
      seen.add(p.stem)
      with Image.open(p) as im:
        im.load()
        if im.format != "PNG" or "A" not in im.getbands() or im.width<9 or im.height<9 or im.getchannel("A").getbbox() is None: fail(f"invalid transparent PNG {p.name}")
    bases={x[:-2] if x.endswith('-2') else x for x in seen}
    bad=sorted(b for b in bases if b not in seen or b+'-2' not in seen)
    if bad: fail("incomplete pose pairs: "+", ".join(bad))
    return files
def main():
 p=argparse.ArgumentParser(); p.add_argument("library",choices=["standard","fun","wes"]); p.add_argument("--source",type=Path,required=True); p.add_argument("--revision"); p.add_argument("--keep",type=int,default=4); args=p.parse_args()
 source=args.source.resolve(); files=validate(source); revision=args.revision or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
 if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}",revision): p.error("invalid revision")
 root=ROOT/"assets"/"illustration-releases"/args.library; root.mkdir(parents=True,exist_ok=True); target=root/revision
 if target.exists(): fail(f"release exists: {target}")
 with tempfile.TemporaryDirectory(prefix="release-",dir=root) as temp:
  stage=Path(temp)/revision; art=stage/"illustrations"; shutil.copytree(source,art); validate(art)
  subprocess=[sys.executable,str(ROOT/"scripts"/"build_masks.py"),"--illustrations",str(art),"--frontend",str(stage)]
  import subprocess as sp; sp.run(subprocess,check=True,timeout=180)
  dims=json.loads((stage/"dims.json").read_text()); masks=json.loads((stage/"masks.json").read_text())
  if set(dims)!=set(masks) or set(dims)!={x.stem for x in files}: fail("metadata does not match images")
  digest=hashlib.sha256()
  for f in sorted(art.glob("*.png")): digest.update(f.name.encode()); digest.update(f.read_bytes())
  manifest={"schema":1,"library":args.library,"revision":revision,"published_at":datetime.now(timezone.utc).isoformat(),"files":len(files),"content_sha256":digest.hexdigest()}
  (stage/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
  stage.rename(target)
 current=root/"CURRENT"; swap=root/".CURRENT.new"; swap.write_text(revision+"\n"); os.replace(swap,current)
 old=sorted([x for x in root.iterdir() if x.is_dir() and not x.name.startswith('.')],key=lambda x:x.name)
 for x in old[:-args.keep]: shutil.rmtree(x)
 print(json.dumps(manifest))
 return 0
if __name__=='__main__':
 try: raise SystemExit(main())
 except Exception as e: print(f"error: {e}",file=sys.stderr); raise SystemExit(1)

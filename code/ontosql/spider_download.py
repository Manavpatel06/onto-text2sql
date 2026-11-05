"""Download Spider 1.0 (Yu et al., EMNLP 2018) into data/spider/.

Works on Windows, macOS and Linux with only the standard library.
By default only the dev split is kept (dev.json, tables.json and the 20 dev
databases, ~120 MB on disk); pass keep="all" for the full 1.8 GB.
"""

from __future__ import annotations

import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

SPIDER_URL = (
    "https://drive.usercontent.google.com/download?"
    "id=1403EGqzIDoHMdQF4c9Bkyl7dZLZ5Wt6J&export=download&confirm=t"
)
TOP_FILES = {"dev.json", "tables.json", "dev_gold.sql", "README.txt", "train_spider.json"}


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=120) as r, tmp.open("wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  downloading {done >> 20} / {total >> 20} MB", end="", file=sys.stderr)
    print(file=sys.stderr)
    tmp.replace(dest)


def get_spider(target: str | Path, keep: str = "dev", url: str = SPIDER_URL, keep_zip: bool = False) -> Path:
    target = Path(target)
    if (target / "dev.json").exists() and (target / "database").exists():
        print(f"{target} already has Spider; nothing to do")
        return target
    zpath = target.parent / "spider.zip"
    if not zpath.exists():
        print(f"Downloading Spider (~200 MB) to {zpath}")
        _download(url, zpath)
    with zipfile.ZipFile(zpath) as z:
        names = [n for n in z.namelist() if not n.startswith("__MACOSX")]
        root = names[0].split("/")[0]  # "spider_data"
        dev_dbs = {d["db_id"] for d in json.loads(z.read(f"{root}/dev.json"))}
        target.mkdir(parents=True, exist_ok=True)
        n = 0
        for name in names:
            rel = name[len(root) + 1 :]
            if not rel or name.endswith("/"):
                continue
            parts = rel.split("/")
            wanted = (
                (len(parts) == 1 and parts[0] in TOP_FILES)
                or (parts[0] == "database" and (keep == "all" or parts[1] in dev_dbs))
                or (keep == "all" and parts[0] in ("test_database",))
                or (keep == "all" and len(parts) == 1)
            )
            if not wanted:
                continue
            out = target.joinpath(*parts)
            out.parent.mkdir(parents=True, exist_ok=True)
            with z.open(name) as src, out.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            n += 1
    if not keep_zip:
        zpath.unlink()
    n_db = len([p for p in (target / "database").iterdir() if p.is_dir()])
    print(f"Spider ready in {target}: {n} files, {n_db} databases")
    return target

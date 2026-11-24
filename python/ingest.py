"""
Step 1 - Ingest public CMS hospital datasets into data/raw/.

Each source is resolved at run time from the CMS catalog APIs, so the script
keeps working when CMS publishes a new version and the file URL changes:

  * Provider Data Catalog (PDC) datasets are looked up through the DKAN
    metastore API:  https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/<id>
  * The Medicare "Inpatient Hospitals - by Provider and Service" dataset is
    looked up in the data.cms.gov DCAT catalog (https://data.cms.gov/data.json),
    picking the most recent data year.

If discovery fails, a pinned fallback URL (the version this project was built
on) is used. If the download itself fails, the script prints the exact page
to download the file from manually and the filename to save it as.

Raw files are written as  data/raw/<source>_<YYYY-MM-DD>.csv  (download date),
and a provenance manifest is written to docs/source_manifest.json.

Usage:  python python/ingest.py [--force]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
MANIFEST = ROOT / "docs" / "source_manifest.json"

PDC_METASTORE = "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/{id}"
DCAT_CATALOG = "https://data.cms.gov/data.json"
TIMEOUT = 120

SOURCES = {
    "hospital_general_info": {
        "kind": "pdc",
        "pdc_id": "xubh-q36u",
        "landing_page": "https://data.cms.gov/provider-data/dataset/xubh-q36u",
        "fallback_url": "https://data.cms.gov/provider-data/sites/default/files/resources/"
        "d3bf87c5505155f549d603688414f3c6_1793059553/Hospital_General_Information_2.csv",
    },
    "hrrp": {
        "kind": "pdc",
        "pdc_id": "9n3s-kdb3",
        "landing_page": "https://data.cms.gov/provider-data/dataset/9n3s-kdb3",
        "fallback_url": "https://data.cms.gov/provider-data/sites/default/files/resources/"
        "a171bc36c488d3e0dc33ec63abb469a6_1770163617/"
        "FY_2026_Hospital_Readmissions_Reduction_Program_Hospital.csv",
    },
    "mspb": {
        "kind": "pdc",
        "pdc_id": "rrqw-56er",
        "landing_page": "https://data.cms.gov/provider-data/dataset/rrqw-56er",
        "fallback_url": "https://data.cms.gov/provider-data/sites/default/files/resources/"
        "69874ce604586980ac088283c1b35095_1792599862/"
        "Medicare_Hospital_Spending_Per_Patient-Hospital.csv",
    },
    # Added beyond the four core sources: breaks each hospital's MSPB episode
    # spending into claim types (inpatient, SNF, home health, ...), which is
    # what lets us talk about *cost components* of MSPB rather than just the ratio.
    "mspb_by_claim": {
        "kind": "pdc",
        "pdc_id": "nrth-mfg3",
        "landing_page": "https://data.cms.gov/provider-data/dataset/nrth-mfg3",
        "fallback_url": "https://data.cms.gov/provider-data/sites/default/files/resources/"
        "1f8cde9e222d5d49f88a894bcf7a8981_1770163638/Medicare_Hospital_Spending_by_Claim.csv",
    },
    "inpatient_by_provider_service": {
        "kind": "dcat",
        "dcat_title": "Medicare Inpatient Hospitals - by Provider and Service",
        "landing_page": "https://data.cms.gov/provider-summary-by-type-of-service/"
        "medicare-inpatient-hospitals/medicare-inpatient-hospitals-by-provider-and-service",
        "fallback_url": "https://data.cms.gov/sites/default/files/2026-04/"
        "828defb5-c9e6-4442-8c1b-f27bc0799daf/MUP_INP_RY26_P03_V10_DY24_PrvSvc.CSV",
    },
}


def resolve_pdc(cfg: dict) -> dict:
    meta = requests.get(PDC_METASTORE.format(id=cfg["pdc_id"]), timeout=TIMEOUT).json()
    dist = [d for d in meta.get("distribution", []) if d.get("downloadURL", "").lower().endswith(".csv")]
    return {
        "title": meta.get("title"),
        "url": dist[0]["downloadURL"],
        "version": f"modified {meta.get('modified')}",
        "metadata_api": PDC_METASTORE.format(id=cfg["pdc_id"]),
    }


def resolve_dcat(cfg: dict) -> dict:
    catalog = requests.get(DCAT_CATALOG, timeout=TIMEOUT).json()
    best = None
    for ds in catalog["dataset"]:
        if not ds.get("title", "").startswith(cfg["dcat_title"]):
            continue
        for d in ds.get("distribution", []):
            if d.get("format") != "CSV" or not d.get("downloadURL"):
                continue
            # distribution title looks like "<dataset title> : 2024-01-01"
            m = re.search(r"(\d{4}-\d{2}-\d{2})\s*$", d.get("title", ""))
            period = m.group(1) if m else ""
            if best is None or period > best[0]:
                best = (period, d, ds)
    if best is None:
        raise RuntimeError("dataset not found in DCAT catalog")
    period, dist, ds = best
    return {
        "title": dist.get("title"),
        "url": dist["downloadURL"],
        "version": f"data period starting {period}; catalog modified {ds.get('modified')}",
        "metadata_api": DCAT_CATALOG,
    }


def download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(".part")
    with requests.get(url, stream=True, timeout=TIMEOUT) as r:
        r.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
    tmp.rename(dest)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="re-download even if a raw file already exists")
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    manifest, failures = {}, []

    for name, cfg in SOURCES.items():
        existing = sorted(RAW_DIR.glob(f"{name}_[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].csv"))
        if existing and not args.force:
            print(f"[skip] {name}: already have {existing[-1].name} (use --force to refresh)")
            if MANIFEST.exists():
                old = json.loads(MANIFEST.read_text()).get(name)
                if old:
                    manifest[name] = old
            continue

        try:
            info = resolve_pdc(cfg) if cfg["kind"] == "pdc" else resolve_dcat(cfg)
        except Exception as exc:  # network / schema change
            print(f"[warn] {name}: catalog lookup failed ({exc}); using pinned fallback URL")
            info = {"title": name, "url": cfg["fallback_url"], "version": "pinned fallback", "metadata_api": None}

        dest = RAW_DIR / f"{name}_{today}.csv"
        print(f"[get ] {name}: {info['url']}")
        try:
            download(info["url"], dest)
        except Exception as exc:
            failures.append((name, cfg, info, dest, exc))
            continue

        manifest[name] = {
            **info,
            "landing_page": cfg["landing_page"],
            "file": str(dest.relative_to(ROOT)),
            "downloaded": today,
            "bytes": dest.stat().st_size,
            "sha256": sha256(dest),
        }
        print(f"[ ok ] {name}: {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")

    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")

    if failures:
        print("\nSome downloads failed. Download these files manually:")
        for name, cfg, info, dest, exc in failures:
            print(f"  - {name}: {exc}\n      page: {cfg['landing_page']}\n      file: {info['url']}"
                  f"\n      save as: {dest}")
        return 1
    print(f"\nManifest written to {MANIFEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

def normalize_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure all expected keys exist; convert types when possible.
    """
    normalized = {
        "property_id": rec.get("property_id"),
        "title": rec.get("title"),
        "description": rec.get("description") or "",
        "location": rec.get("location"),
        "region_id": rec.get("region_id"),
        "check_in": rec.get("check_in"),
        "check_out": rec.get("check_out"),
        "price": rec.get("price"),
        "amenities": rec.get("amenities") or [],
        "policies": rec.get("policies"),
        "reviews": rec.get("reviews") or [],
        "gallery": rec.get("gallery") or [],
        "offers": rec.get("offers") or [],
        "availability": rec.get("availability"),
        "landmarks": rec.get("landmarks") or [],
        "faq": rec.get("faq") or [],
        "url": rec.get("url"),
    }
    return normalized

def write_json(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with open(path, "w", newline="", encoding="utf-8") as f:
            pass
        return
    keys = sorted({k for r in rows for k in r.keys()})
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({**r, **{k: json.dumps(r[k]) if isinstance(r[k], (list, dict)) else r[k] for k in r}})
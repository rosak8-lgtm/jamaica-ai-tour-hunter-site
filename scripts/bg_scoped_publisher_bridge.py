"""V91: load trusted scoped staging and append paired fresh public evidence.

No provider I/O, no private data in output. Missing or invalid scoped state
must not interrupt the existing Irkutsk catalog. Only the local bot can write
the owner-only staging contract; a search registry alone never yields cards.
"""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import stat

from scripts.bg_scoped_public_projection import project
from scripts.bg_scoped_evidence import MAX_BYTES, instant
from scripts.bot_visual_sidecar import MAX_PUBLIC_RECORDS, validate_public_feed

NAME = re.compile(r"([0-9]{7,20})-([0-9]{7,20})\.json\Z")
MAX_FILES = 1000
MAX_READ_BYTES = 64_000_000

def private_json(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o077 or info.st_nlink != 1
            or not 2 <= info.st_size <= limit):
            raise ValueError("SCOPED_PRIVATE_FILE_UNSAFE")
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("SCOPED_PRIVATE_FILE_OVERSIZE")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError("SCOPED_PRIVATE_JSON_INVALID")
    return obj, len(raw)

def private_directory(path):
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
        or info.st_mode & 0o077):
        raise ValueError("SCOPED_PRIVATE_DIRECTORY_UNSAFE")

def extend(published, visual, directory, registry_path, staging_root, *, now):
    """Return feed, proof, exact admitted ID->scope map, and safe counters.

    Existing public records have priority. Non-Irkutsk rows enter only as
    complete row/proof pairs from V90, with a 30 second publication reserve.
    Invalid scope files are isolated; duplicate IDs never overwrite a row.
    """
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("CLOCK_REQUIRED")
    now = now.astimezone(timezone.utc)
    stats = {"status":"NO_STAGING", "files":0, "rejected":0, "added":0}
    if not validate_public_feed(visual, now=now):
        raise ValueError("LEGACY_VISUAL_INVALID")
    root = Path(staging_root)
    try:
        private_directory(root)
    except FileNotFoundError:
        return published, visual, {}, stats
    except (OSError, ValueError):
        stats["status"] = "STAGING_UNSAFE"
        return published, visual, {}, stats
    try:
        rp = Path(registry_path)
        private_directory(rp.parent)
        registry, _ = private_json(rp, 4_000_000)
        entries = []
        with os.scandir(root) as scan:
            for item in scan:
                if not NAME.fullmatch(item.name):
                    continue
                if len(entries) >= MAX_FILES:
                    raise ValueError("SCOPED_FILE_LIMIT")
                info = item.stat(follow_symlinks=False)
                entries.append((info.st_mtime_ns, item.name))
    except (OSError, ValueError, TypeError):
        stats["status"] = "REGISTRY_OR_STAGING_HOLD"
        return published, visual, {}, stats
    stats["status"] = "SCANNED"
    rows = list(published["previews"])
    proofs = list(visual["entries"])
    used = {r["id"] for r in rows} | {p["preview_id"] for p in proofs}
    admitted = {}
    remaining = MAX_READ_BYTES
    for _, name in sorted(entries, reverse=True):
        if len(proofs) >= MAX_PUBLIC_RECORDS or len(rows) >= 60_000:
            break
        if remaining < 2:
            stats["status"] = "READ_BUDGET_REACHED"
            break
        stats["files"] += 1
        try:
            staged, size = private_json(root / name, min(MAX_BYTES, remaining))
            remaining -= size
            match = NAME.fullmatch(name)
            if (staged.get("origin_id"), staged.get("country_id")) != match.groups():
                raise ValueError("SCOPED_FILENAME_MISMATCH")
            candidates, evidence = project(staged, registry, directory, now=now)
            if len(candidates) != len(evidence):
                raise ValueError("SCOPED_PAIR_MISMATCH")
        except (OSError, ValueError, TypeError, KeyError, AttributeError, StopIteration):
            stats["rejected"] += 1
            continue
        for row, proof in zip(candidates, evidence):
            ident = row["id"]
            seen = instant(proof["observed_at_utc"])
            if (ident in used or ident != proof["preview_id"] or seen is None
                or not -30 <= (now-seen).total_seconds() <= 870
                or row["price_observed_at_utc"] != proof["observed_at_utc"]):
                continue
            if len(proofs) >= MAX_PUBLIC_RECORDS or len(rows) >= 60_000:
                break
            rows.append(row)
            proofs.append(proof)
            used.add(ident)
            admitted[ident] = (row["origin"], row["country"])
    if not admitted:
        return published, visual, {}, stats
    result_visual = {**visual, "entries": proofs}
    if not validate_public_feed(result_visual, now=now):
        stats["status"] = "SCOPED_FINAL_PROOF_HOLD"
        return published, visual, {}, stats
    stats["added"] = len(admitted)
    counts = Counter(r["country"] for r in rows)
    result = {**published, "previews":rows,
              "indicative_two_adult_rub_count":sum(
                  r.get("price_source") == "BG_EXACT_SELECTED_GREEN_BROWSER"
                  for r in rows)}
    if isinstance(published.get("countries_status"), list):
        result["countries_status"] = [
            {**x,"previews":counts.get(x.get("country"),0)} if isinstance(x,dict) else x
            for x in published["countries_status"]]
    return result, result_visual, admitted, stats

#!/usr/bin/env python3
"""Introspect V183 bot RESULT CONTRACT without executing a supplier browser.

Strictly local and read only: no network, imports of source, subprocess,
Telegram, writes, passwords, cookies or DOM text output. Extracts ONLY
allowlisted function names, public-safe dictionary key NAMES and call names
from whitelisted Python functions and JS identifier tokens.
"""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
import re

ROOT_NAME="JAMAICA_V183_DUAL_TELEGRAM_DELIVERY_20261123"
FILES={
    "bg_browser_v148.py":(
        "calendar_diverse_markers","next_marker_window","price_class",
        "send_best_observed","send_ranked","render_live","render","run_cycle"
    ),
    "bg_catalog_v148.py":(
        "best_price","parse_price_list","scout"
    ),
    "visual_bridge_v148.py":(
        "inspect_snapshot","make_message"
    ),
    "capture_bg_v148.js":()
}
PUBLIC_KEYS=frozenset((
    "country","country_name","origin","departure","date","tour_date",
    "date_from","date_to","depart_date","return_date","night","nights",
    "hotel","hotel_id","room","meal","route","route_id","marker",
    "best_price","best_price_label_verified","best_price_flag",
    "both_green","both_green_flights_verified","green_flights",
    "flight_out","flight_back","flight_to","flight_return","price",
    "price_rub","total_rub","currency","source","url","status","reason",
    "verified","checked","observed","availability","isstop","rows",
    "candidates","records","matches","entries","payload","result",
    "source_price_list_id","id_price","date_iso","source_preview_id"
))
CALLS=frozenset((
    "click","evaluate","locator","get_by_text","get_by_role","goto",
    "best_price","inspect_snapshot","make_message","parse_price_list",
    "send_best_observed","send_ranked","render_live","render",
    "run_cycle","scout","next_marker_window","calendar_diverse_markers",
    "price_class","flight_pair_evidence"
))
MAX_BYTES=220000

def safe_file(path:Path):
    if path.is_symlink() or not path.is_file():
        return None
    try:
        if not 1<=path.stat().st_size<=MAX_BYTES:
            return None
        return path.read_bytes()
    except OSError:
        return None

def python_summary(data:bytes,allowed_names:tuple):
    text=data.decode("utf-8")
    tree=ast.parse(text)
    out=[]
    for node in ast.walk(tree):
        if (not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) or
            node.name not in allowed_names):
            continue
        names=set()
        calls=set()
        for child in ast.walk(node):
            if isinstance(child,ast.Dict):
                for key in child.keys:
                    if (isinstance(key,ast.Constant) and
                        isinstance(key.value,str) and
                        key.value in PUBLIC_KEYS):
                        names.add(key.value)
            if isinstance(child,ast.Call):
                f=child.func
                name=f.id if isinstance(f,ast.Name) else (
                    f.attr if isinstance(f,ast.Attribute) else "")
                if name in CALLS:
                    calls.add(name)
        out.append({"function":node.name,"line":node.lineno,
                    "safe_result_keys":sorted(names)[:35],
                    "safe_calls":sorted(calls)[:25]})
    return sorted(out,key=lambda x:x["line"])

def js_summary(data:bytes):
    txt=data.decode("utf-8")
    # Only report allowlisted identifier NAMES; no source substrings or values.
    return {"allowlisted_identifiers":[k for k in sorted(PUBLIC_KEYS)
            if re.search(r"(?<![A-Za-z0-9_])"+re.escape(k)+
                         r"(?![A-Za-z0-9_])",txt)][:45],
            "browser_call_names":[x for x in sorted(CALLS)
                                  if re.search(r"\b"+re.escape(x)+r"\b",txt)]}

def inspect(base:Path):
    root=base/ROOT_NAME
    if root.is_symlink() or not root.is_dir():
        return []
    result=[]
    for name,fn_names in FILES.items():
        blob=safe_file(root/name)
        if blob is None:
            continue
        try:
            summary=(python_summary(blob,fn_names) if name.endswith(".py") else
                     js_summary(blob))
        except (UnicodeError,SyntaxError):
            continue
        result.append({
          "file":name,
          "sha256_prefix":hashlib.sha256(blob).hexdigest()[:16],
          "contract":summary,
        })
    return result

def main():
    result=inspect(Path.home()/"Загрузки")
    print("JAMAICA_V183_BOT_SOURCE_CONTRACT_READONLY_V1")
    for row in result:
        print("V183_CONTRACT="+json.dumps(row,ensure_ascii=False,
                                         separators=(",",":")))
    print("FILES_INSPECTED="+str(len(result)))
    print("BOT_CODE_RUN=NO")
    print("NETWORK_OR_TELEGRAM=NO")
    print("SECRET_SOURCE_TEXT_OR_VALUES_EXPORTED=NO")
    print("LIVE_BOT_TO_SITE_EVIDENCE_PRODUCER_CONNECTED=NO")
    return 0 if result else 2

if __name__=="__main__":
    raise SystemExit(main())

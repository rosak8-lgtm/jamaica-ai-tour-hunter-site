#!/usr/bin/env python3
"""Read-only source fingerprint audit of the *installed Lenovo BG browser bot*.

Does not import, execute, deploy, modify, screenshot, authenticate or open a
browser. Scans a tiny bounded allowlist of user-owned bot release directories
and prints only source filenames, AST function identifiers, hashes and
presence of route-badge/plane/click tokens. NO SOURCE TEXT or secrets appear.

Run from Lenovo in the separate JAMAICA site repo. This is deliberately
not a claim that we have executed or independently inspected the Lenovo files.
"""
from __future__ import annotations
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT_NAMES=(
    "JAMAICA_V183_DUAL_TELEGRAM_DELIVERY_20261123",
    "JAMAICA_V167_BG_VERIFIABLE_FUNNEL_20261122",
    "JAMAICA_V6511_BG_VISUAL_EVIDENCE_20261112",
    "JAMAICA_12_81J_DIRECT_ROW_BINDING",
    "JAMAICA_12_81V_BEST_PRICE_PRIORITY",
    "JAMAICA_12_81G_ROW_STRIP_EVIDENCE",
)
SOURCE_SUFFIXES={".py",".js"}
EXCLUDE={"node_modules","venv",".venv",".git","__pycache__",
         "logs","secrets","data","dist","build","fixtures"}
BEST=re.compile(r"ЛУЧШАЯ\s+ЦЕНА|best.?price|best_price_label_verified",re.I)
GREEN=re.compile(r"both.?green|green.?flight|flight.?green|самол[её]т",re.I)
CLICK=re.compile(r"\.click\s*\(|\.tap\s*\(|\.dispatch_event\s*\(",re.I)
BROWSER=re.compile(r"playwright|puppeteer|selenium|page\.locator|page\.evaluate",re.I)
MAX_FILES=600
MAX_BYTES=240000

def inspect_source(path:Path)->dict|None:
    if path.is_symlink() or path.suffix.lower() not in SOURCE_SUFFIXES:
        return None
    try:
        size=path.stat().st_size
        if not 1<=size<=MAX_BYTES:
            return None
        raw=path.read_bytes()
        text=raw.decode("utf-8")
    except (ValueError,UnicodeError,OSError):
        return None
    bm=bool(BEST.search(text))
    gm=bool(GREEN.search(text))
    cm=bool(CLICK.search(text))
    browser=bool(BROWSER.search(text))
    if not (bm or gm):
        return None
    functions=[]
    if path.suffix==".py":
        try:
            tree=ast.parse(text)
        except SyntaxError:
            tree=None
        if tree:
            for node in ast.walk(tree):
                if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                    continue
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}",node.name):
                    continue
                # Read only parsed function lines. No source is displayed.
                if not hasattr(node,"end_lineno"):continue
                snippet="\n".join(text.splitlines()[node.lineno-1:node.end_lineno])
                if BEST.search(snippet) or GREEN.search(snippet):
                    functions.append({
                        "name":node.name,"line":node.lineno,
                        "best_price":bool(BEST.search(snippet)),
                        "both_flights":bool(GREEN.search(snippet)),
                        "click":bool(CLICK.search(snippet)),
                    })
    return {
        "sha256_prefix":hashlib.sha256(raw).hexdigest()[:16],
        "best_price":bm,
        "green_flights":gm,
        "browser":browser,
        "click":cm,
        "functions":sorted(functions,key=lambda x:x["line"])[:12],
    }

def inspect_roots(base:Path):
    result=[];scanned=0
    for root_name in ROOT_NAMES:
        root=base/root_name
        if not root.is_dir() or root.is_symlink():
            continue
        for folder,dirs,names in os.walk(root,followlinks=False):
            depth=len(Path(folder).parts)-len(root.parts)
            dirs[:]=sorted(x for x in dirs if x not in EXCLUDE and
                           not (Path(folder)/x).is_symlink()) if depth<3 else []
            for name in sorted(names):
                if scanned>=MAX_FILES:
                    return result,scanned,True
                path=Path(folder)/name
                if path.suffix not in SOURCE_SUFFIXES:
                    continue
                scanned+=1
                summary=inspect_source(path)
                if summary:
                    summary["file"]=str(path.relative_to(base))
                    result.append(summary)
    result.sort(key=lambda x:(
        -(int(x["best_price"])+int(x["green_flights"])),
        -int(x["browser"] and x["click"]),
        x["file"]
    ))
    return result,scanned,False

def main():
    base=Path.home()/"Загрузки"
    results,scanned,truncated=inspect_roots(base)
    print("JAMAICA_BOT_ROUTE_FIRST_SOURCE_READ_ONLY_V1")
    print("BOT_SOURCE_FILES_SCANNED="+str(scanned))
    print("BOT_SOURCE_SCAN_TRUNCATED="+str(truncated))
    print("BOT_SOURCE_CANDIDATES="+str(len(results)))
    for x in results[:18]:
        print("BOT_CANDIDATE="+json.dumps(x,ensure_ascii=False,separators=(",",":")))
    print("NO_BOT_CODE_EXECUTED_NO_SECRETS_OR_SOURCE_TEXT_EXPORTED=YES")
    if not results:
        print("BOT_SOURCE_LOCATION_HOLD=NO_SOURCE_IN_KNOWN_RELEASE_DIRECTORIES")
        return 2
    # AST features alone are NOT proof that the operator was contacted.
    print("BOT_RUNTIME_BEST_PRICE_THEN_TWO_GREEN_VERIFIED=NO")
    return 0

if __name__=="__main__":
    sys.exit(main())

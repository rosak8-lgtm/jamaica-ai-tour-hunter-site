#!/usr/bin/env python3
"""Daily HBX photo sync ON ORACLE. Caller must hold the catalog refresh.lock.

Only a site-scoped written photo license + exact, evidence-backed property ID map
may trigger publication. The normal five-minute price importer stays independent.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime,timezone

import oracle_site_publisher as site
from hbx_licensed_hotel_photos import load_json,license_gate,verified_map,MediaHold

PRIVATE=Path.home()/".config"/"jamaica-hbx"
GRANT=PRIVATE/"grant.json"
MAP=PRIVATE/"crosswalk.json"

def log(name,value):
    print("JAMAICA_HBX_"+name+"="+str(value),flush=True)

def run(args,*,cwd,env=None,timeout=2400):
    proc=subprocess.run(args,cwd=cwd,env=env,capture_output=True,
                        text=True,timeout=timeout,check=False)
    # Only purpose-built status lines; suppress all network errors, passwords,
    # supplier hotel data and private license/crosswalk contents.
    if proc.returncode:
        raise MediaHold("PHOTO_IMPORT_OR_GIT_COMMAND_FAILED")
    for line in proc.stdout.splitlines():
        if line.startswith("JAMAICA_HBX_") and len(line)<180:
            print(line,flush=True)
    return proc.stdout

def main():
    if not GRANT.is_file() or not MAP.is_file():
        log("HOLD","PRIVATE_GRANT_OR_CROSSWALK_MISSING")
        return
    for path in (GRANT,MAP):
        if path.is_symlink() or path.stat().st_mode & 0o077:
            raise MediaHold("PRIVATE_HBX_MATERIAL_PERMISSIONS_NOT_600")
    grant=load_json(GRANT,limit=10000)
    license_gate(grant)
    env=dict(os.environ)
    if len(env.get("HBX_API_KEY",""))<8 or len(env.get("HBX_API_SECRET",""))<8:
        log("HOLD","API_CREDENTIALS_MISSING")
        return
    # The independent Oracle repository is already pinned to a verified key.
    git_env=site.git_env()
    site.checkout(git_env)
    directory=load_json(site.CHECKOUT/"destination-directory.json",limit=32_000_000)
    verified_map(load_json(MAP,limit=8_000_000),directory)
    args=[sys.executable,"-B",str(site.CHECKOUT/"scripts"/"hbx_licensed_hotel_photos.py"),
         "--directory",str(site.CHECKOUT/"destination-directory.json"),
         "--crosswalk",str(MAP),"--grant",str(GRANT),
         "--output-dir",str(site.CHECKOUT),"--live","--max-pages","250"]
    run(args,cwd=site.CHECKOUT,env=env,timeout=2100)
    dirty=run(["git","status","--porcelain","--","hotel-media-feed"],
               cwd=site.CHECKOUT,env=git_env,timeout=30)
    if not dirty.strip():
        log("PUBLISH","UNCHANGED")
        return
    run(["git","add","-A","--","hotel-media-feed"],
        cwd=site.CHECKOUT,env=git_env,timeout=30)
    diff=subprocess.run(["git","diff","--cached","--quiet"],cwd=site.CHECKOUT,
                        env=git_env,capture_output=True,timeout=30)
    if diff.returncode==0:
        log("PUBLISH","UNCHANGED")
        return
    if diff.returncode!=1:
        raise MediaHold("GIT_DIFF_FAILED")
    run(["git","-c","user.name=JAMAICA Licensed Media",
         "-c","user.email=jamaica-licensed-media@users.noreply.github.com",
         "commit","-m","Update licensed HBX hotel photo URLs for JAMAICA"],
        cwd=site.CHECKOUT,env=git_env,timeout=30)
    # No force push: fail safely if five-minute catalog imported meanwhile.
    run(["git","push","origin","HEAD:refs/heads/main"],
        cwd=site.CHECKOUT,env=git_env,timeout=90)
    log("PUBLISH","PUSHED_LICENSED_EXTERNAL_MEDIA_ONLY")
    log("PUBLISHED_AT",datetime.now(timezone.utc).isoformat(timespec="seconds"))

if __name__=="__main__":
    try:main()
    except (MediaHold,site.CatalogHold,OSError,ValueError,KeyError,
            subprocess.TimeoutExpired) as exc:
        log("HOLD",str(exc) if isinstance(exc,(MediaHold,site.CatalogHold)) else
             type(exc).__name__)
        sys.exit(2)

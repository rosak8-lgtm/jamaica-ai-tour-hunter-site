#!/usr/bin/env python3
"""Server-local JAMAICA read-only import + source-backed GitHub Pages publishing.

- Runs entirely ON ORACLE (ubuntu). Lenovo not involved after installation.
- Authenticated tour price-list GETs; NEVER supplier booking/payments.
- Publishes only sanitized existing public feed/directory to one pinned repo.
- Uses a repository-scoped write deploy key (not a personal GitHub API token).
- Skips commits if unchanged; publishes a heartbeat at most every 30 minutes.
- Rolls back to previously verified public feed on API/validation failures.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPOSITORY = "git@github.com:rosak8-lgtm/jamaica-ai-tour-hunter-site.git"
RUNROOT = Path.home()/".local"/"share"/"jamaica-oracle-catalog"
CHECKOUT = RUNROOT/"site"
KEY = Path.home()/".ssh"/"jamaica_catalog_deploy_ed25519"
KNOWN_HOSTS = Path.home()/".ssh"/"jamaica_catalog_known_hosts"
# After the first updated installation, the server reads source adapters from
# its verified GitHub clone, so future catalog fixes apply automatically.
SCRIPTS = CHECKOUT/"scripts"
DISCOVERY_STATE = RUNROOT/"extra_irkutsk_source_countries.json"
MAX_BYTES = 8_000_000
MAX_ITEMS = 8_000
HEARTBEAT = timedelta(minutes=30)
MAX_DIRECTORY_AGE = timedelta(days=7)
DIRECTORY_REFRESH = timedelta(hours=24)
SAFE_LOG = re.compile(r"^(JAMAICA_|COUNTRY_[0-9]+(?:_[-A-Z_]+)?=|COUNTRIES_|PREVIEW_COUNT=|INDICATIVE_|PRICE_LISTS_|STATUS_|PUBLIC_PREVIEWS_|ROWS_SCANNED_|HOTEL_IDS_MATCHED_|NO_CONFIRMED_)")

class CatalogHold(Exception):
    pass

def log(key,value):
    print(f"{key}={value}",flush=True)

def run(args, *, cwd=None, env=None, timeout=180, expose=False, check=True):
    result=subprocess.run(args,cwd=cwd,env=env,timeout=timeout,
                          text=True,capture_output=True,check=False)
    if expose:
        for line in result.stdout.splitlines():
            if SAFE_LOG.match(line) and len(line)<240:
                print(line,flush=True)
    if check and result.returncode:
        raise CatalogHold("STEP_FAILED_"+str(args[0]).replace("/","_"))
    return result

def git_env():
    if not KEY.is_file() or not KNOWN_HOSTS.is_file():
        raise CatalogHold("SSH_DEPLOY_KEY_OR_PINNED_HOST_MISSING")
    if KEY.stat().st_mode & 0o077:
        raise CatalogHold("DEPLOY_KEY_PERMISSIONS_NOT_PRIVATE")
    env=dict(os.environ)
    env["GIT_SSH_COMMAND"]=(
        "ssh -F /dev/null -o BatchMode=yes -o IdentitiesOnly=yes "
        "-o StrictHostKeyChecking=yes "
        f"-o UserKnownHostsFile={KNOWN_HOSTS} "
        f"-o ConnectTimeout=15 -i {KEY}")
    env["GIT_TERMINAL_PROMPT"]="0"
    return env

def checkout(env):
    RUNROOT.mkdir(parents=True,exist_ok=True)
    RUNROOT.chmod(0o700)
    if not (CHECKOUT/".git").exists():
        if CHECKOUT.exists():
            raise CatalogHold("WORKTREE_EXISTS_NOT_A_GIT_CLONE")
        run(["git","clone","--depth=1","--branch","main",REPOSITORY,str(CHECKOUT)],
            env=env,timeout=90)
    remote=run(["git","remote","get-url","origin"],cwd=CHECKOUT,env=env).stdout.strip()
    if remote!=REPOSITORY:
        raise CatalogHold("UNEXPECTED_GIT_REMOTE")
    # The dedicated worktree contains only generated public files, no user edits.
    run(["git","fetch","--depth=1","origin","main"],cwd=CHECKOUT,env=env,timeout=90)
    run(["git","checkout","--force","-B","main","origin/main"],cwd=CHECKOUT,env=env)
    run(["git","reset","--hard","origin/main"],cwd=CHECKOUT,env=env)

def timestamp(value):
    try:
        result=datetime.fromisoformat(value.replace("Z","+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (AttributeError,TypeError,ValueError):
        return None

def directory_check(directory):
    if directory.get("schema")!="jamaica.destination-directory.v1":
        raise CatalogHold("DIRECTORY_SCHEMA_INVALID")
    countries=directory.get("countries",[])
    hotels=directory.get("hotels",[])
    if not (180<=len(countries)<=400 and 500<=len(hotels)<=120000):
        raise CatalogHold("DIRECTORY_SIZE_INVALID")
    updated=timestamp(directory.get("updated_at_utc"))
    if not updated or datetime.now(timezone.utc)-updated>MAX_DIRECTORY_AGE:
        raise CatalogHold("DIRECTORY_EXPIRED")
    return updated

def refresh_directory():
    target=CHECKOUT/"destination-directory.json"
    directory=json.loads(target.read_text(encoding="utf-8"))
    updated=directory_check(directory)
    if datetime.now(timezone.utc)-updated<DIRECTORY_REFRESH:
        return False
    # Fetch the public country + hotel directory; fall back to previous valid
    # copy if its age is below 7 days and the public endpoint is temporarily down.
    proc=run([sys.executable,"-B",str(SCRIPTS/"sync_destination_directory.py")],
             cwd=CHECKOUT,timeout=130,check=False)
    if proc.returncode:
        log("JAMAICA_DIRECTORY_REFRESH","SOURCE_ERROR_KEEP_LAST_VALID")
        return False
    new=json.loads(target.read_text(encoding="utf-8"))
    directory_check(new)
    log("JAMAICA_DIRECTORY_REFRESH","UPDATED")
    return True

def validate(feed, directory):
    if not isinstance(feed,dict) or feed.get("schema")!="jamaica.tour-previews.v1":
        raise CatalogHold("FEED_SCHEMA_INVALID")
    if feed.get("bookable") is not False or feed.get("quote_verified") is not False or feed.get("availability_verified") is not False:
        raise CatalogHold("FEED_FALSE_BOOKING_CLAIM")
    rows=feed.get("previews")
    if not isinstance(rows,list) or not 0<len(rows)<=MAX_ITEMS:
        raise CatalogHold("FEED_ROWS_INVALID")
    known={c.get("name") for c in directory["countries"] if isinstance(c,dict)}
    seen=set()
    allowed={"id","hotel_id","hotel","country","origin","resort","room","depart_date","nights",
             "status","price_reference_rub","price_reference_party","quote_verified",
             "availability_verified","flight_verified","bookable"}
    for row in rows:
        if not isinstance(row,dict) or set(row)!=allowed:
            raise CatalogHold("FEED_UNAPPROVED_FIELDS")
        if row.get("bookable") is not False or row.get("flight_verified") is not False or row.get("quote_verified") is not False or row.get("availability_verified") is not False:
            raise CatalogHold("FEED_UNVERIFIED_STOCK")
        if row.get("country") not in known or row.get("origin")!="Иркутск":
            raise CatalogHold("FEED_WRONG_ORIGIN")
        if not isinstance(row.get("id"),str) or not re.fullmatch(r"p_[a-f0-9]{24}",row["id"]):
            raise CatalogHold("FEED_INVALID_ID")
        if row["id"] in seen:
            raise CatalogHold("FEED_DUPLICATE_ID")
        seen.add(row["id"])
        amt=row.get("price_reference_rub")
        if amt is not None:
            if type(amt) is not int or not 0<amt<=100_000_000 or row.get("price_reference_party")!="TWO_ADULTS":
                raise CatalogHold("FEED_PRICE_INVALID")
        elif row.get("price_reference_party")!="UNVERIFIED":
            raise CatalogHold("FEED_PARTY_INVALID")
    refreshed=timestamp(feed.get("refreshed_at_utc"))
    if not refreshed or abs((datetime.now(timezone.utc)-refreshed).total_seconds())>300:
        raise CatalogHold("FEED_NOT_FRESH_FROM_SUPPLIER")
    return len(rows)

def comparable(feed):
    # Ignore timestamps and unstable ordering of country probes; never ignore
    # price, hotel, date, room, stop or source coverage changes.
    return {
        "previews":feed.get("previews"),
        "countries_status":feed.get("countries_status"),
    }

def needs_publish(previous,current,*,now=None):
    now=now or datetime.now(timezone.utc)
    if not isinstance(previous,dict):
        return True
    if comparable(previous)!=comparable(current):
        return True
    prev_time=timestamp(previous.get("refreshed_at_utc"))
    return not prev_time or now-prev_time>=HEARTBEAT

def update_discovered_source_countries(feed,directory,*,state_path=DISCOVERY_STATE):
    """Promote any actual Irkutsk price-list country to the 5-minute core scan.

    Keep only country names, never prices, URLs, cookies or supplier identifiers.
    """
    old=[]
    if state_path.is_file():
        if state_path.is_symlink() or state_path.stat().st_size>10000:
            raise CatalogHold("DISCOVERY_STATE_INVALID")
        value=json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(value,list) or len(value)>40:
            raise CatalogHold("DISCOVERY_STATE_SCHEMA_INVALID")
        old=[v for v in value if isinstance(v,str)]
    source={c["name"] for c in directory["countries"]
            if isinstance(c,dict) and c.get("has_tour_catalog") and
            "100510397223" not in c.get("origins",[]) and isinstance(c.get("name"),str)}
    names=set(old)&source
    for st in feed.get("countries_status",[]):
        if isinstance(st,dict) and st.get("country") in source and
                type(st.get("lists_read")) is int and st["lists_read"]>0:
            names.add(st["country"])
    updated=sorted(names)[:40]
    if old!=updated:
        target=state_path.with_suffix(".tmp")
        target.write_text(json.dumps(updated,ensure_ascii=False)+"\\n",encoding="utf-8")
        target.chmod(0o600)
        target.replace(state_path)
    return len(updated)


def publish(env):
    # Destination directory is in this clone. Source secrets remain outside Git.
    refresh_directory()
    directory=json.loads((CHECKOUT/"destination-directory.json").read_text(encoding="utf-8"))
    directory_check(directory)
    feed_path=CHECKOUT/"tour-previews.json"
    previous=json.loads(feed_path.read_text(encoding="utf-8")) if feed_path.is_file() else None
    generated=RUNROOT/"generated-tour-previews.json"
    if generated.exists():
        generated.unlink()
    command=[sys.executable,"-B",str(SCRIPTS/"oracle_bg_preview_export.py"),
             "--directory",str(CHECKOUT/"destination-directory.json"),
             "--output",str(generated),"--max-countries","120",
             "--per-country","5","--discover-state",str(DISCOVERY_STATE)]
    run(command,cwd=SCRIPTS,timeout=200,expose=True)
    if not generated.is_file() or generated.stat().st_size>MAX_BYTES:
        raise CatalogHold("GENERATED_FEED_INVALID_SIZE")
    new=json.loads(generated.read_text(encoding="utf-8"))
    count=validate(new,directory)
    promoted=update_discovered_source_countries(new,directory)
    log("JAMAICA_SOURCE_COUNTRIES_TOTAL",new.get("source_scope",{}).get("source_tour_countries","UNKNOWN"))
    log("JAMAICA_OTHER_COUNTRIES_PROBED",new.get("source_scope",{}).get("other_countries_probed_this_cycle","UNKNOWN"))
    log("JAMAICA_DISCOVERED_EXTRA_COUNTRIES",promoted)
    log("JAMAICA_PUBLIC_PREVIEWS_TRUNCATED",new.get("truncated_to_public_limit",False))
    log("JAMAICA_ORACLE_COUNTRY_COUNT",len({x["country"] for x in new["previews"]}))
    log("JAMAICA_ORACLE_TOUR_COUNT",count)
    log("JAMAICA_ORACLE_INDICATIVE_RUB_COUNT",sum(type(x["price_reference_rub"]) is int for x in new["previews"]))
    changed_dir=bool(run(["git","status","--porcelain","--","destination-directory.json"],
                         cwd=CHECKOUT,env=env).stdout.strip())
    if not changed_dir and not needs_publish(previous,new):
        log("JAMAICA_ORACLE_PUBLISH","NO_CHANGE_GITHUB_COMMIT_SKIPPED")
        return
    # Write only generated PUBLIC source-backed JSON after strict validation.
    feed_path.write_bytes(generated.read_bytes())
    run(["git","add","--","tour-previews.json","destination-directory.json"],cwd=CHECKOUT,env=env)
    staged=run(["git","diff","--cached","--quiet"],cwd=CHECKOUT,env=env,check=False)
    if staged.returncode==0:
        log("JAMAICA_ORACLE_PUBLISH","NOTHING_TO_COMMIT")
        return
    if staged.returncode!=1:
        raise CatalogHold("GIT_DIFF_FAILED")
    run(["git","-c","user.name=JAMAICA Oracle Catalog",
         "-c","user.email=jamaica-oracle-catalog@users.noreply.github.com",
         "commit","-m","Update verified-source Jamaica travel catalog on Oracle 5m schedule"],
        cwd=CHECKOUT,env=env)
    # If another process pushed meanwhile, stop instead of force-pushing.
    run(["git","push","origin","HEAD:refs/heads/main"],cwd=CHECKOUT,env=env,timeout=90)
    log("JAMAICA_ORACLE_PUBLISH","PUSHED_TO_GITHUB_PAGES_SOURCE")
    log("JAMAICA_LAST_PUBLISH_AT_UTC",datetime.now(timezone.utc).isoformat(timespec="seconds"))

def main():
    log("JAMAICA_ORACLE_5MIN_IMPORT_START",datetime.now(timezone.utc).isoformat(timespec="seconds"))
    env=git_env()
    checkout(env)
    publish(env)
    log("JAMAICA_ORACLE_5MIN_IMPORT_PASS","YES")

if __name__=="__main__":
    try:
        main()
    except (CatalogHold,subprocess.TimeoutExpired,ValueError,KeyError,OSError) as exc:
        # NEVER dump URLs, passwords, cookie values, or raw supplier/PSP responses.
        message=exc.args[0] if isinstance(exc,CatalogHold) else type(exc).__name__
        log("JAMAICA_ORACLE_5MIN_IMPORT_HOLD",message)
        sys.exit(2)

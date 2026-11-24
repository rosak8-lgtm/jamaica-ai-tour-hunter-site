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
from collections import deque
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

# The installed Oracle service script may live outside the GitHub clone:
# prefer audited, freshly fetched helpers from that pinned checkout.
_REPO_SCRIPTS=Path.home()/".local"/"share"/"jamaica-oracle-catalog"/"site"/"scripts"
if _REPO_SCRIPTS.is_dir():
    sys.path.insert(0,str(_REPO_SCRIPTS))
else:
    sys.path.insert(0,str(Path(__file__).resolve().parent))
import recent_preview_catalog as recent
import catalog_size_budget as byte_limit
import bot_visual_sidecar as visual
import public_tour_eligibility as eligibility
import site_bot_price_overlay as browser_price
import catalog_property_identity as identity

REPOSITORY = "git@github.com:rosak8-lgtm/jamaica-ai-tour-hunter-site.git"
RUNROOT = Path.home()/".local"/"share"/"jamaica-oracle-catalog"
CHECKOUT = RUNROOT/"site"
KEY = Path.home()/".ssh"/"jamaica_catalog_deploy_ed25519"
KNOWN_HOSTS = Path.home()/".ssh"/"jamaica_catalog_known_hosts"
# After the first updated installation, the server reads source adapters from
# its verified GitHub clone, so future catalog fixes apply automatically.
SCRIPTS = CHECKOUT/"scripts"
DISCOVERY_STATE = RUNROOT/"extra_irkutsk_source_countries.json"
RECENT_SOURCE_CACHE = RUNROOT/"recent-price-list-previews.json"
PRIVATE_BOT_VISUAL_RECEIPTS = RUNROOT/"private-bg-route-first-receipts.json"
PRIVATE_SITE_DOM_PRICES = RUNROOT/"private-site-bot-dom-prices.json"
PUBLIC_VISUAL_PATH = "tour-visual-evidence.json"
MAX_BYTES = 45_000_000
MAX_ITEMS = 60_000
ROOT_ITEMS = 8_000
SHARD_ITEMS = 4_000
MAX_SHARDS = 13
SHARD_FOLDER = "tour-previews-shards"
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

def validate(feed, directory, *, allow_empty=False, allow_browser_prices=False):
    if not isinstance(feed,dict) or feed.get("schema")!="jamaica.tour-previews.v1":
        raise CatalogHold("FEED_SCHEMA_INVALID")
    if feed.get("bookable") is not False or feed.get("quote_verified") is not False or feed.get("availability_verified") is not False:
        raise CatalogHold("FEED_FALSE_BOOKING_CLAIM")
    rows=feed.get("previews")
    if not isinstance(rows,list) or not len(rows)<=MAX_ITEMS or (not rows and not allow_empty):
        raise CatalogHold("FEED_ROWS_INVALID")
    known={c.get("name") for c in directory["countries"] if isinstance(c,dict)}
    seen=set()
    allowed={"id","hotel_id","hotel","country","origin","resort","room","depart_date","nights",
             "status","price_reference_rub","price_reference_party","quote_verified",
             "availability_verified","flight_verified","bookable"}
    for row in rows:
        if not isinstance(row,dict) or (set(row)!=allowed and not (
            allow_browser_prices and set(row)==allowed|{"price_source","price_observed_at_utc"})):
            raise CatalogHold("FEED_UNAPPROVED_FIELDS")
        if "price_source" in row:
            observed=timestamp(row.get("price_observed_at_utc"))
            if (row["price_source"]!="BG_EXACT_SELECTED_GREEN_BROWSER" or
                row.get("status")!="REFERENCE_PRICE_LIST_ONLY" or
                type(row.get("price_reference_rub")) is not int or
                not observed or not -30<=(datetime.now(timezone.utc)-observed).total_seconds()<=900):
                raise CatalogHold("FEED_BROWSER_PRICE_INVALID")
        if row.get("bookable") is not False or row.get("flight_verified") is not False or row.get("quote_verified") is not False or row.get("availability_verified") is not False:
            raise CatalogHold("FEED_UNVERIFIED_STOCK")
        if row.get("country") not in known or row.get("origin")!="Иркутск":
            raise CatalogHold("FEED_WRONG_ORIGIN")
        if not isinstance(row.get("id"),str) or not re.fullmatch(r"p_[a-f0-9]{24}",row["id"]):
            raise CatalogHold("FEED_INVALID_ID")
        if row["id"] in seen:
            raise CatalogHold("FEED_DUPLICATE_ID")
        seen.add(row["id"])
        if row.get("status") not in (
            "REFERENCE_PRICE_LIST_ONLY",recent.HISTORICAL_STATUS):
            raise CatalogHold("FEED_UNKNOWN_PREVIEW_STATUS")
        if row["status"]==recent.HISTORICAL_STATUS and (
            row.get("price_reference_rub") is not None or
            row.get("price_reference_party")!="UNVERIFIED"):
            raise CatalogHold("FEED_STALE_PRICE_FORBIDDEN")
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

def load_recent_source_cache(path=RECENT_SOURCE_CACHE):
    """Owner-only source-memory file; invalid files cannot influence public data."""
    if not path.exists() and not path.is_symlink():
        return None
    st=path.lstat()
    if (path.is_symlink() or not path.is_file() or
        st.st_uid!=os.geteuid() or st.st_mode & 0o077 or
        not 2<=st.st_size<=MAX_BYTES):
        raise CatalogHold("PRIVATE_SOURCE_CACHE_PERMISSIONS_OR_SIZE")
    try:
        obj=json.loads(path.read_text(encoding="utf-8"))
    except (ValueError,UnicodeError):
        raise CatalogHold("PRIVATE_SOURCE_CACHE_JSON_INVALID") from None
    if not isinstance(obj,dict) or obj.get("schema")!=recent.CACHE_SCHEMA:
        raise CatalogHold("PRIVATE_SOURCE_CACHE_SCHEMA_INVALID")
    return obj


def save_recent_source_cache(data,path=RECENT_SOURCE_CACHE):
    """Atomic private state; only published/successfully reconciled sources."""
    if path.is_symlink():
        raise CatalogHold("PRIVATE_SOURCE_CACHE_SYMLINK")
    content=json.dumps(data,ensure_ascii=False,separators=(",",":")).encode("utf-8")
    if not 2<=len(content)<=MAX_BYTES:
        raise CatalogHold("PRIVATE_SOURCE_CACHE_TOO_LARGE")
    fd,tmp_name=tempfile.mkstemp(prefix=".jamaica-recent-",dir=path.parent)
    tmp=Path(tmp_name)
    try:
        with os.fdopen(fd,"wb") as stream:
            os.fchmod(stream.fileno(),0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp,path)
    finally:
        if tmp.exists():
            tmp.unlink()


def comparable(feed):
    # Ignore timestamps and unstable ordering of country probes; never ignore
    # price, hotel, date, room, stop or source coverage changes.
    return {
        "previews":feed.get("previews"),
        "shards":feed.get("shards",[]),
        "total_published_previews":feed.get("total_published_previews",len(feed.get("previews",[]))),
        "truncated_to_public_limit":feed.get("truncated_to_public_limit"),
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

def diverse_root_and_remaining(rows,root_limit=ROOT_ITEMS):
    """Move authentic diverse country/month source rows into the fast root.

    The exporter sorts all rows primarily by departure date; rows[:8000]
    could contain almost exclusively nearby departures and hide remote
    countries or December/2027 tours until up to 13 network files load.
    This is a STABLE partition: every source row appears exactly once,
    with no fabricated country/date/price or changes to verification flags.

    Fair allocation is by country, then by actual departure month. Within
    each country/month prioritize current, known-price reference options,
    preserving price/date ordering and original index for deterministic ties.
    """
    if type(root_limit) is not int or root_limit<1 or root_limit>ROOT_ITEMS:
        raise CatalogHold("ROOT_COUNTRY_BUDGET_INVALID")
    if len(rows)<=root_limit:
        return list(rows),[]
    grouped={}
    for index,row in enumerate(rows):
        grouped.setdefault(row["country"],{}).setdefault(
            row["depart_date"][:7],[]).append(index)
    priority={"Таиланд":0,"Китай":1,"Вьетнам":2}
    groups={}
    for country,months in grouped.items():
        ordered={}
        for month,indices in months.items():
            indices.sort(key=lambda i:(
                rows[i].get("status")!="REFERENCE_PRICE_LIST_ONLY",
                rows[i].get("price_reference_rub") is None,
                rows[i].get("price_reference_rub") or 100_000_001,
                rows[i]["depart_date"],i
            ))
            ordered[month]=deque(indices)
        groups[country]=(ordered,deque(sorted(months)))
    countries=deque(sorted(groups,key=lambda c:(
        priority.get(c,999),c)))
    picked=[]
    while countries and len(picked)<root_limit:
        country=countries.popleft()
        month_options,active_months=groups[country]
        month=active_months.popleft()
        options=month_options[month]
        picked.append(options.popleft())
        if options:
            active_months.append(month)
        if active_months:
            countries.append(country)
    selected=set(picked)
    return [rows[i] for i in picked],[row for i,row in enumerate(rows)
                                       if i not in selected]


def make_sharded_catalog(feed):
    """Publish ≤8k fast initial rows plus bounded separate source-backed shards.

    The root JSON is compatible with old readers. Manifest hashes are based
    on *rows alone*, so timestamp-only server probes do not create commits
    every five minutes. All assets are staged in ONE Git commit.
    """
    rows=feed.get("previews")
    if not isinstance(rows,list) or len(rows)>MAX_ITEMS:
        raise CatalogHold("CATALOG_SHARD_SOURCE_SIZE_INVALID")
    root=dict(feed)
    root_rows,remainder=diverse_root_and_remaining(rows,ROOT_ITEMS)
    root["previews"]=root_rows
    root["total_published_previews"]=len(rows)
    manifest=[]
    chunks={}
    for i,offset in enumerate(range(0,len(remainder),SHARD_ITEMS),start=1):
        if i>MAX_SHARDS:
            raise CatalogHold("TOO_MANY_PUBLIC_SHARDS")
        part=remainder[offset:offset+SHARD_ITEMS]
        path=f"{SHARD_FOLDER}/part-{i:03d}.json"
        signature=hashlib.sha256(json.dumps(part,ensure_ascii=False,
            sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()
        manifest.append({"path":path,"count":len(part),"sha256":signature})
        chunks[path]={"schema":"jamaica.tour-preview-shard.v1",
            "refreshed_at_utc":feed["refreshed_at_utc"],
            "bookable":False,"quote_verified":False,
            "availability_verified":False,"previews":part}
    root["shards"]=manifest
    if sum(item["count"] for item in manifest)+len(root["previews"])!=len(rows):
        raise CatalogHold("SHARD_COUNTS_MISMATCH")
    return root,chunks


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
        if (isinstance(st,dict) and st.get("country") in source and
                type(st.get("lists_read")) is int and st["lists_read"]>0):
            names.add(st["country"])
    updated=sorted(names)[:40]
    if old!=updated:
        target=state_path.with_suffix(".tmp")
        target.write_text(json.dumps(updated,ensure_ascii=False)+"\n",encoding="utf-8")
        target.chmod(0o600)
        target.replace(state_path)
    return len(updated)


def refresh_source_feed(directory):
    """Preserve the last complete private feed during a new operator scan.

    The independent browser process is a concurrent reader. Do not unlink
    its input before fetching a replacement. Use a private staging directory
    and atomically promote only a successful, validated fresh source feed.
    On failure the previous file and its original timestamp remain unchanged.
    """
    generated=RUNROOT/"generated-tour-previews.json"
    if generated.is_symlink():
        raise CatalogHold("GENERATED_FEED_UNSAFE_TARGET")
    with tempfile.TemporaryDirectory(prefix=".source-scan-",dir=RUNROOT) as work:
        staged=Path(work)/"generated-tour-previews.json"
        command=[sys.executable,"-B",str(SCRIPTS/"oracle_bg_preview_export.py"),
                 "--directory",str(CHECKOUT/"destination-directory.json"),
                 "--output",str(staged),"--max-countries","120",
                 "--per-country","5","--discover-state",str(DISCOVERY_STATE)]
        run(command,cwd=SCRIPTS,timeout=200,expose=True)
        if not staged.is_file() or staged.is_symlink():
            raise CatalogHold("GENERATED_FEED_MISSING_OR_UNSAFE")
        generated_bytes=staged.stat().st_size
        log("JAMAICA_GENERATED_FEED_BYTES",generated_bytes)
        if not 100<=generated_bytes<=MAX_BYTES:
            raise CatalogHold("GENERATED_FEED_EMPTY_OR_OVERSIZED")
        new=json.loads(staged.read_text(encoding="utf-8"))
        validate(new,directory)
        identity.verify_catalog_hotel_identity(new["previews"],directory)
        staged.chmod(0o600)
        os.replace(staged,generated)
    log("JAMAICA_PRIVATE_SOURCE_ATOMIC_REPLACE","PASS")
    return new

def merge_exact_browser_source(feed, directory, receipts, *, path=None, now=None):
    """Accept a bounded private source handoff only with current exact proof.
    The website bot independently fetched the exact clicked BG price list.
    This does not authorize source-only rows or historical prices.
    """
    path=path or RUNROOT/"private-site-exact-source.json"
    now=now or datetime.now(timezone.utc)
    try:
        fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|os.O_NONBLOCK)
        try:
            import stat
            st=os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_uid!=os.geteuid() or
                st.st_mode&0o077 or not 2<=st.st_size<=2_000_000):
                raise ValueError("UNSAFE_EXACT_SOURCE")
            with os.fdopen(fd,"rb",closefd=False) as stream:
                raw=stream.read(2_000_001)
        finally:os.close(fd)
        if len(raw)>2_000_000:raise ValueError("EXACT_SOURCE_SIZE")
        payload=json.loads(raw)
        if (not isinstance(payload,dict) or set(payload)!={"schema","records"} or
            payload["schema"]!="jamaica.bg-site-exact-source.v1" or
            not isinstance(payload["records"],list) or len(payload["records"])>1000):
            raise ValueError("EXACT_SOURCE_SCHEMA")
    except FileNotFoundError:return feed,0
    except (OSError,ValueError,TypeError):
        log("JAMAICA_EXACT_SOURCE_STATUS","INVALID_IGNORE")
        return feed,0
    from backend.bg_route_first_visual_gate import route_first_pair_matches
    proofs={x.get("preview_id"):x for x in (receipts or {}).get("records",[])
            if isinstance(x,dict) and isinstance(x.get("preview_id"),str)}
    accepted={}
    known=identity.build_hotel_index(directory)
    for record in payload["records"]:
        if not isinstance(record,dict) or set(record)!={"preview","source_price_list_id","observed_at_utc"}:continue
        row=record["preview"]
        if not isinstance(row,dict):continue
        try:
            validate({**feed,"previews":[row]},directory)
            if (row["status"]!="REFERENCE_PRICE_LIST_ONLY" or
                row["price_reference_rub"] is not None or row["price_reference_party"]!="UNVERIFIED" or
                not all(isinstance(row[k],str) and row[k] for k in
                        ("country","hotel_id","depart_date","room")) or
                type(row["nights"]) is not int or not 3<=row["nights"]<=180):
                continue
            key="|".join((row["country"],row["hotel_id"],row["depart_date"],str(row["nights"]),row["room"]))
            if row["id"]!="p_"+hashlib.sha256(key.encode()).hexdigest()[:24]:continue
            departure=datetime.fromisoformat(row["depart_date"]).date()
            if not now.date()<=departure<=now.date()+timedelta(days=180):continue
            p=proofs.get(row["id"],{})
            route,flight=p.get("route"),p.get("flight")
            if not route_first_pair_matches(route,flight,row,now=now):continue
            if (route.get("source_price_list_id")!=record["source_price_list_id"] or
                flight.get("flight_checked_at_utc")!=record["observed_at_utc"]):continue
            if known.get(row["hotel_id"])!=(row["hotel"],row["country"]) or row["origin"]!="Иркутск":continue
            accepted[row["id"]]=row
        except (ValueError,TypeError,KeyError,CatalogHold):continue
    if not accepted:return feed,0
    combined=list(accepted.values())+[r for r in feed["previews"] if r["id"] not in accepted]
    return {**feed,"previews":combined[:MAX_ITEMS]},len(accepted)


def publish(env):
    # Destination directory is in this clone. Source secrets remain outside Git.
    refresh_directory()
    directory=json.loads((CHECKOUT/"destination-directory.json").read_text(encoding="utf-8"))
    directory_check(directory)
    feed_path=CHECKOUT/"tour-previews.json"
    previous=json.loads(feed_path.read_text(encoding="utf-8")) if feed_path.is_file() else None
    new=refresh_source_feed(directory)
    previous_cache=load_recent_source_cache()
    if previous_cache is not None:
        raw_entries=previous_cache.get("entries")
        if not isinstance(raw_entries,list) or len(raw_entries)>MAX_ITEMS or any(
            not isinstance(e,dict) or set(e)!={"row","last_seen_at_utc"}
            for e in raw_entries):
            raise CatalogHold("PRIVATE_SOURCE_CACHE_ENTRIES_INVALID")
        cached_rows=[e["row"] for e in raw_entries]
        if cached_rows:
            validate({**new,"previews":cached_rows},directory)
    new,next_cache=recent.combine(new,previous_cache,max_rows=MAX_ITEMS)
    new,dropped_by_budget=byte_limit.fit_feed(new,max_bytes=32_000_000)
    # Never accumulate private history entries that failed the public byte cap.
    retained_ids={item["id"] for item in new["previews"]}
    next_cache={**next_cache,"entries":[item for item in next_cache["entries"]
                if item["row"]["id"] in retained_ids]}
    log("JAMAICA_PREVIEWS_DROPPED_BY_BYTE_BUDGET",dropped_by_budget)
    count=validate(new,directory)
    # Fail closed BEFORE Git staging and publication if ANY of the up to
    # 60,000 source-backed hotel cards mismatches the official hotel ID/name/
    # country crosswalk. Do not guess or silently swap properties/photos.
    proof=identity.verify_catalog_hotel_identity(new["previews"],directory)
    log("JAMAICA_HOTEL_IDENTITY_VERIFIED_ROWS",proof["checked"])
    log("JAMAICA_HOTEL_IDENTITY_VERIFIED_COUNTRIES",proof["countries"])
    # Build only PRIVATE source candidates until the bot has independently
    # checked the selected route's badge and both flight icons.
    # Optional authenticated V183 browser-event bridge. A file from the bot
    # MUST be owner-only, have exact source lineage, and be <=15 minutes old.
    # A missing, invalid or untrusted proof cannot stall public tour browsing.
    try:
        private_receipts=visual.read_private_receipts(PRIVATE_BOT_VISUAL_RECEIPTS)
        new,exact_count=merge_exact_browser_source(new,directory,private_receipts)
        count=validate(new,directory)
        log("JAMAICA_SITE_EXACT_SOURCE_ROWS",exact_count)
        visual_public=visual.build_visual_feed(
            new["previews"],private_receipts)
    except (visual.VisualHold,ValueError,TypeError):
        visual_public=visual.empty_public()
        log("JAMAICA_BOT_VISUAL_STATUS","RECEIPTS_INVALID_IGNORE")
    if not visual.validate_public_feed(visual_public):
        visual_public=visual.empty_public()
    published=eligibility.select_public_source_rows(new,visual_public)
    # A source XML amount can change many times per day. Never display that
    # amount as a fresh verified-tour price. Only the trusted website bot's
    # independently tied same-session DOM amount may replace it.
    try:
        trusted_browser_prices=browser_price.read_ledger(PRIVATE_SITE_DOM_PRICES)
    except (ValueError,OSError):
        trusted_browser_prices=None
        log("JAMAICA_WEBSITE_BOT_PRICE_STATUS","PRIVATE_LEDGER_INVALID_HIDE_PRICE")
    published=browser_price.apply(published,
        private_receipts if "private_receipts" in locals() else None,
        visual_public,trusted_browser_prices)
    log("JAMAICA_SITE_LIVE_DOM_PRICES",published["indicative_two_adult_rub_count"])
    public_root,public_chunks=make_sharded_catalog(published)
    validate(public_root,directory,allow_empty=True,allow_browser_prices=True)
    log("JAMAICA_PUBLIC_VISUALLY_VERIFIED_TOURS",len(published["previews"]))
    log("JAMAICA_PUBLIC_HIDDEN_UNVERIFIED",len(new["previews"])-len(published["previews"]))
    visual_path=CHECKOUT/PUBLIC_VISUAL_PATH
    try:
        previous_visual=json.loads(visual_path.read_text(encoding="utf-8")
            ) if visual_path.is_file() and not visual_path.is_symlink() else None
    except (ValueError,UnicodeError,OSError):
        previous_visual=None
    visual_changed=previous_visual!=visual_public
    log("JAMAICA_VISUAL_ROUTE_FIRST_MATCHES",len(visual_public["entries"]))
    promoted=update_discovered_source_countries(new,directory)
    log("JAMAICA_SOURCE_COUNTRIES_TOTAL",new.get("source_scope",{}).get("source_tour_countries","UNKNOWN"))
    log("JAMAICA_OTHER_COUNTRIES_PROBED",new.get("source_scope",{}).get("other_countries_probed_this_cycle","UNKNOWN"))
    log("JAMAICA_DISCOVERED_EXTRA_COUNTRIES",promoted)
    log("JAMAICA_PUBLIC_PREVIEWS_TRUNCATED",new.get("truncated_to_public_limit",False))
    log("JAMAICA_ORACLE_COUNTRY_COUNT",len({x["country"] for x in new["previews"]}))
    log("JAMAICA_ORACLE_TOUR_COUNT",count)
    log("JAMAICA_PUBLIC_SHARD_COUNT",len(public_chunks))
    log("JAMAICA_RECENT_UNRECHECKED_PREVIEWS",
        new["source_scope"]["last_24h_unrechecked_previews"])
    log("JAMAICA_RECENT_UNRECHECKED_COUNTRIES",
        new["source_scope"]["last_24h_unrechecked_countries"])
    log("JAMAICA_ORACLE_INDICATIVE_RUB_COUNT",sum(type(x["price_reference_rub"]) is int for x in new["previews"]))
    changed_dir=bool(run(["git","status","--porcelain","--","destination-directory.json"],
                         cwd=CHECKOUT,env=env).stdout.strip())
    if not changed_dir and not visual_changed and not needs_publish(previous,public_root):
        save_recent_source_cache(next_cache)
        log("JAMAICA_ORACLE_PUBLISH","NO_CHANGE_GITHUB_COMMIT_SKIPPED")
        return
    # Keep the legacy fast index small; publish the remainder in verifiable
    # sibling chunks. All URLs are pinned filenames from our own generator.
    target_folder=CHECKOUT/SHARD_FOLDER
    if target_folder.is_symlink():
        raise CatalogHold("PUBLIC_SHARD_FOLDER_SYMLINK")
    target_folder.mkdir(exist_ok=True)
    expected=set()
    aggregate_size=0
    for rel,chunk in public_chunks.items():
        path=CHECKOUT/rel
        if path.is_symlink() or path.parent!=target_folder:
            raise CatalogHold("UNSAFE_SHARD_OUTPUT_PATH")
        data=json.dumps(chunk,ensure_ascii=False,separators=(",",":")).encode("utf-8")+b"\n"
        if len(data)>4_000_000:
            raise CatalogHold("SHARD_TOO_LARGE")
        aggregate_size+=len(data)
        path.write_bytes(data)
        expected.add(path.name)
    for stale in target_folder.glob("part-*.json"):
        if stale.name not in expected:
            if stale.is_symlink():raise CatalogHold("STALE_SHARD_SYMLINK")
            stale.unlink()
    root_bytes=json.dumps(public_root,ensure_ascii=False,separators=(",",":")).encode("utf-8")+b"\n"
    if len(root_bytes)>8_000_000 or aggregate_size+len(root_bytes)>MAX_BYTES:
        raise CatalogHold("PUBLIC_BUNDLE_TOO_LARGE")
    feed_path.write_bytes(root_bytes)
    if visual_path.is_symlink():
        raise CatalogHold("PUBLIC_VISUAL_FEED_SYMLINK")
    visual_bytes=json.dumps(visual_public,ensure_ascii=False,
        separators=(",",":")).encode("utf-8")+b"\n"
    if len(visual_bytes)>100_000:
        raise CatalogHold("PUBLIC_VISUAL_FEED_TOO_LARGE")
    visual_path.write_bytes(visual_bytes)
    run(["git","add","-A","--","tour-previews.json","destination-directory.json",SHARD_FOLDER,PUBLIC_VISUAL_PATH],
        cwd=CHECKOUT,env=env)
    staged=run(["git","diff","--cached","--quiet"],cwd=CHECKOUT,env=env,check=False)
    if staged.returncode==0:
        save_recent_source_cache(next_cache)
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
    save_recent_source_cache(next_cache)
    log("JAMAICA_ORACLE_PUBLISH","PUSHED_TO_GITHUB_PAGES_SOURCE")
    log("JAMAICA_LAST_PUBLISH_AT_UTC",datetime.now(timezone.utc).isoformat(timespec="seconds"))

def discover_hotel_media_daily():
    """Stage official hotelPic URLs in a PRIVATE rights-pending inventory.

    Does NOT publish, show, download, cache, or grant rights to images.
    Failure never changes the actual sales catalog or its 5-minute timer.
    """
    last=RUNROOT/".hotel-media-last-attempt"
    now=datetime.now(timezone.utc).timestamp()
    if last.is_file() and now-last.stat().st_mtime<24*3600:
        return
    last.touch(mode=0o600,exist_ok=True)
    os.chmod(last,0o600)
    destination=RUNROOT/"private-hotel-media-candidates.json"
    args=[
        sys.executable,"-B",str(SCRIPTS/"oracle_bg_hotel_media_candidates.py"),
        "--directory",str(CHECKOUT/"destination-directory.json"),
        "--output-private",str(destination),
    ]
    try:
        outcome=run(args,cwd=SCRIPTS,timeout=55,check=False,expose=True)
        if outcome.returncode:
            log("JAMAICA_HOTEL_MEDIA_DISCOVERY","SOURCE_UNAVAILABLE_OR_SCHEMA_CHANGED")
        else:
            log("JAMAICA_HOTEL_MEDIA_DISCOVERY","PRIVATE_CANDIDATES_ONLY")
    except (subprocess.TimeoutExpired,OSError):
        log("JAMAICA_HOTEL_MEDIA_DISCOVERY","TEMPORARILY_UNAVAILABLE")


def main():
    log("JAMAICA_ORACLE_5MIN_IMPORT_START",datetime.now(timezone.utc).isoformat(timespec="seconds"))
    env=git_env()
    checkout(env)
    publish(env)
    discover_hotel_media_daily()
    log("JAMAICA_ORACLE_5MIN_IMPORT_PASS","YES")

if __name__=="__main__":
    try:
        main()
    except (CatalogHold,subprocess.TimeoutExpired,ValueError,KeyError,OSError) as exc:
        # NEVER dump URLs, passwords, cookie values, or raw supplier/PSP responses.
        message=exc.args[0] if isinstance(exc,CatalogHold) else type(exc).__name__
        log("JAMAICA_ORACLE_5MIN_IMPORT_HOLD",message)
        sys.exit(2)

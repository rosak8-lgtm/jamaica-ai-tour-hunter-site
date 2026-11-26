"""Read-only owner preflight. No contacts, network, listener, database or writes.

Passing this check does not establish legal compliance or a reachable public
endpoint. TLS/proxy integration and end-to-end acceptance remain separate.
"""
import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from backend.customer_inquiry_catalog import LocalCatalog, read
from backend.customer_inquiry_store import ID, VERSION

def https_url(value, expected_path=None):
    if not isinstance(value,str) or not value or len(value)>2048:return False
    if any(ord(c)<33 for c in value):return False
    try:
        u=urlsplit(value)
        return bool(u.scheme=="https" and u.hostname and not u.username and
                    not u.password and not u.query and not u.fragment and
                    (expected_path is None or u.path==expected_path))
    except ValueError:return False

def config_status(config,env):
    c=config if isinstance(config,dict) else {}
    seller=c.get("controller_name")
    version=c.get("policy_version")
    return {
        "CONFIG_SCHEMA_VALID":c.get("schema")=="jamaica.inquiry-config.v1",
        "CLIENT_ENABLED":c.get("enabled") is True,
        "PRIVACY_APPROVAL_RECORDED":c.get("privacy_approved") is True,
        "CONTROLLER_CONFIGURED":isinstance(seller,str) and 3<=len(seller.strip())<=200,
        "POLICY_VERSION_VALID":isinstance(version,str) and bool(VERSION.fullmatch(version)),
        "POLICY_URL_CONFIGURED":https_url(c.get("privacy_url")),
        "HTTPS_ENDPOINT_CONFIGURED":https_url(c.get("endpoint"),"/v1/customer-inquiries"),
        "OWNER_LEGAL_FLAG":env.get("JAMAICA_INQUIRY_LEGAL_APPROVED")=="yes",
        "HASH_SECRET_PRESENT":len(env.get("JAMAICA_INQUIRY_HASH_SECRET","").encode())>=32,
        "PROXY_SECRET_PRESENT":len(env.get("JAMAICA_INQUIRY_PROXY_SECRET",""))>=32 and env.get("JAMAICA_INQUIRY_PROXY_SECRET","").isascii(),
    }

def read_state(exc):
    if isinstance(exc,FileNotFoundError):return "ABSENT"
    if isinstance(exc,PermissionError):return "PERMISSION_DENIED"
    if isinstance(exc,ValueError) and str(exc) in ("UNSAFE_FILE","FILE_LIMIT"):return str(exc)
    if isinstance(exc,OSError):return "READ_ERROR"
    return "INVALID_DATA"

def catalog_status(root,now):
    resolver=LocalCatalog(root)
    result={}
    for name,file,limit in (("BG","tour-previews.json",24*1024*1024),
                            ("PEGAS","application-reference.json",12*1024*1024)):
        result[name+"_ROOT_ROWS"]=0
        result[name+"_READ_STATE"]="NOT_READ"
        result[name+"_EXACT_SAMPLE_RESOLVED"]=False
        try:
            feed,_=read(root/file,limit)
            rows=feed.get("previews")
            if not isinstance(rows,list) or len(rows)>8000:
                result[name+"_READ_STATE"]="INVALID_ROWS"
                continue
            result[name+"_READ_STATE"]="OK"
            result[name+"_ROOT_ROWS"]=len(rows)
            ids=[r.get("id") for r in rows if isinstance(r,dict)]
            # At most three independent resolver calls per source, not a full scan.
            for pid in ids[:3]:
                if isinstance(pid,str) and ID.fullmatch(pid) and resolver(pid,now):
                    result[name+"_EXACT_SAMPLE_RESOLVED"]=True
                    break
        except (OSError,ValueError,TypeError,KeyError,AttributeError,RecursionError) as exc:
            result[name+"_READ_STATE"]=read_state(exc)
    return result

def report(root,*,now,env):
    root=Path(root)
    try:
        config,_=read(root/"inquiry-config.json",32768)
        config_read_state="OK" if isinstance(config,dict) else "INVALID_DATA"
    except (OSError,ValueError,TypeError,RecursionError) as exc:
        config={}
        config_read_state=read_state(exc)
    flags=config_status(config,env)
    counts=catalog_status(root,now)
    return {"classification":"READ_ONLY_PREFLIGHT_NOT_PRODUCTION_ACCEPTANCE",
            "configuration":flags,"config_read_state":config_read_state,"catalog":counts,
            "missing":[k for k,v in flags.items() if not v],
            "config_checks_pass":all(flags.values()),
            "public_endpoint_tested":False,"legal_compliance_verified":False,
            "booking_enabled_by_this_check":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--catalog",type=Path,required=True)
    args=p.parse_args()
    try:r=report(args.catalog,now=datetime.now(timezone.utc),env=os.environ)
    except (OSError,ValueError,TypeError):raise SystemExit("JAMAICA_INQUIRY_PREFLIGHT_HOLD")
    print(json.dumps(r,ensure_ascii=False,indent=2))
if __name__=="__main__":main()

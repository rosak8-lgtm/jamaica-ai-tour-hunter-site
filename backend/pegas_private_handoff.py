"""Read only the dedicated, owner-controlled normalized PEGAS evidence file.

Never infer evidence from a Telegram message, search listing or public feed.
The browser producer must explicitly implement this contract and atomically
replace its private file. No network, supplier requests or booking actions.
"""
import json
import os
import stat
from pathlib import Path
from backend.pegas_public_projection import MAX_ROWS, build_catalog

SCHEMA="jamaica.pegas-private-handoff.v1"
MAX_BYTES=16_000_000

def read_pairs(path):
    path=Path(path)
    parent=path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=os.geteuid() or parent.st_mode&0o077:
        raise ValueError("PEGAS_PRIVATE_DIRECTORY_UNSAFE")
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,"rb") as stream:
        info=os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or
            stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1 or info.st_size>MAX_BYTES):
            raise ValueError("PEGAS_PRIVATE_FILE_UNSAFE")
        data=stream.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:raise ValueError("PEGAS_PRIVATE_FILE_TOO_LARGE")
    obj=json.loads(data)
    if not isinstance(obj,dict) or set(obj)!={"schema","pairs"} or obj["schema"]!=SCHEMA:
        raise ValueError("PEGAS_PRIVATE_SCHEMA_INVALID")
    pairs=obj["pairs"]
    if not isinstance(pairs,list) or len(pairs)>MAX_ROWS:
        raise ValueError("PEGAS_PRIVATE_BATCH_INVALID")
    if any(not isinstance(p,list) or len(p)!=2 or any(not isinstance(x,dict) for x in p) for p in pairs):
        raise ValueError("PEGAS_PRIVATE_PAIR_INVALID")
    return pairs

def project_file(path,*,now):
    """Return status plus sanitized public rows; invalid data fails closed."""
    try:
        pairs=read_pairs(path)
        return "VERIFIED_PROJECTION",build_catalog(pairs,now=now)
    except FileNotFoundError:
        return "PRIVATE_HANDOFF_MISSING",build_catalog([],now=now)
    except (OSError,ValueError,TypeError,UnicodeError,RecursionError):
        return "PRIVATE_HANDOFF_INVALID",build_catalog([],now=now)

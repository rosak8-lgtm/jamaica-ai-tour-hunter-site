"""Private, durable BG multi-origin scheduling foundation (V35).
No supplier calls, no publication, no systemd changes.
Only a single cooperating browser consumer may use this queue. Existing
workers must be coordinated by an external shared lock before activation.
"""
from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from scripts.bg_origin_scope import Scope

PRIORITIES=("Иркутск","Красноярск","Новосибирск","Улан-удэ","Москва","Санкт-Петербург","Екатеринбург")
COUNTRIES=("Таиланд","Китай","Вьетнам")
RESULTS=frozenset({"OBSERVED","NO_MATCH","LOCAL_HOLD","PROVIDER_COOLDOWN","FAILED"})
def _epoch(now):
    if not isinstance(now,datetime) or now.tzinfo is None:
        raise ValueError("AWARE_CLOCK_REQUIRED")
    return int(now.timestamp())

class OriginQueue:
    def __init__(self,path,*,global_gap=180):
        if type(global_gap) is not int or global_gap<180:
            raise ValueError("GLOBAL_GAP_MINIMUM_180")
        self.global_gap=global_gap
        self.db=sqlite3.connect(str(path),timeout=10,isolation_level=None)
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS scopes(
          origin_id TEXT,country_id TEXT,origin TEXT,country TEXT,
          priority INTEGER NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,
          last_attempt INTEGER, next_due INTEGER NOT NULL DEFAULT 0,
          last_result TEXT, PRIMARY KEY(origin_id,country_id));
        CREATE TABLE IF NOT EXISTS control(
          singleton INTEGER PRIMARY KEY CHECK(singleton=1),
          next_allowed INTEGER NOT NULL DEFAULT 0, token TEXT,
          origin_id TEXT,country_id TEXT, claimed_at INTEGER);
        INSERT OR IGNORE INTO control(singleton) VALUES(1);
        """)
    def close(self):
        self.db.close()
    @contextmanager
    def _tx(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.rollback()
            raise
        else:
            self.db.commit()
    def sync(self,registry):
        if not isinstance(registry,dict) or not isinstance(registry.get("pairs"),list):
            raise ValueError("INVALID_REGISTRY")
        if not 1<=len(registry["pairs"])<=10000:
            raise ValueError("REGISTRY_SIZE")
        scopes=[]
        seen=set()
        for pair in registry["pairs"]:
            scope=Scope.from_registry(registry,pair["origin_id"],pair["country_id"])
            key=(scope.origin_id,scope.country_id)
            if key in seen:
                raise ValueError("DUPLICATE_SCOPE")
            seen.add(key)
            scopes.append(scope)
        with self._tx():
            if self.db.execute("SELECT token FROM control").fetchone()[0]:
                raise RuntimeError("ACTIVE_CLAIM")
            self.db.execute("UPDATE scopes SET enabled=0")
            for s in scopes:
                p=(PRIORITIES.index(s.origin) if s.origin in PRIORITIES else len(PRIORITIES))*10
                p+=COUNTRIES.index(s.country) if s.country in COUNTRIES else len(COUNTRIES)
                self.db.execute("""INSERT INTO scopes(origin_id,country_id,origin,country,priority)
                    VALUES(?,?,?,?,?) ON CONFLICT(origin_id,country_id) DO UPDATE SET
                    origin=excluded.origin,country=excluded.country,priority=excluded.priority,enabled=1""",
                    (s.origin_id,s.country_id,s.origin,s.country,p))
        return len(scopes)
    def claim(self,now):
        """One persistent outstanding claim; never silently steal an expired claim."""
        t=_epoch(now)
        with self._tx():
            c=self.db.execute("SELECT * FROM control").fetchone()
            if c["token"] or t<c["next_allowed"]:
                return None
            r=self.db.execute("""SELECT * FROM scopes WHERE enabled=1 AND next_due<=?
                ORDER BY CASE WHEN last_attempt IS NULL THEN 0 ELSE 1 END,
                last_attempt,priority,origin_id,country_id LIMIT 1""",(t,)).fetchone()
            if not r:
                return None
            token=uuid4().hex
            self.db.execute("""UPDATE control SET token=?,origin_id=?,country_id=?,
                claimed_at=?,next_allowed=? WHERE singleton=1""",
                (token,r["origin_id"],r["country_id"],t,t+self.global_gap))
            self.db.execute("UPDATE scopes SET last_attempt=? WHERE origin_id=? AND country_id=?",
                (t,r["origin_id"],r["country_id"]))
            return token,Scope(r["origin_id"],r["origin"],r["country_id"],r["country"])
    def finish(self,token,result,now,*,retry_after=180):
        t=_epoch(now)
        if result not in RESULTS or type(retry_after) is not int or retry_after<180:
            raise ValueError("INVALID_COMPLETION")
        with self._tx():
            c=self.db.execute("SELECT * FROM control").fetchone()
            if not token or c["token"]!=token or t<c["claimed_at"]:
                raise ValueError("INVALID_CLAIM")
            due=t+retry_after
            self.db.execute("""UPDATE scopes SET last_result=?,next_due=?
                WHERE origin_id=? AND country_id=?""",(result,due,c["origin_id"],c["country_id"]))
            # A provider cooldown applies across all cities. A local hold is
            # not evidence of a network search; it is still rate limited.
            next_allowed=max(c["next_allowed"],t+self.global_gap,
                due if result=="PROVIDER_COOLDOWN" else 0)
            self.db.execute("""UPDATE control SET token=NULL,origin_id=NULL,country_id=NULL,
                claimed_at=NULL,next_allowed=? WHERE singleton=1""",(next_allowed,))
    def snapshot(self):
        c=self.db.execute("SELECT token,next_allowed FROM control").fetchone()
        rows=self.db.execute("""SELECT origin,country,last_result,last_attempt,next_due
            FROM scopes WHERE enabled=1 ORDER BY priority,origin,country""").fetchall()
        return {"classification":"SCHEDULER_STATE_NOT_OFFERS","active_claim":bool(c["token"]),
                "next_allowed":c["next_allowed"],"scopes":[dict(r) for r in rows]}

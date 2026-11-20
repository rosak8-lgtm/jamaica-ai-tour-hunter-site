"""Durable private SQLite store for JAMAICA order/account state and notifications.

Runs on server only; NEVER publish or commit its .sqlite database.
No money movement, login, supplier calls, document signing or Telegram here.
Transition is an atomic SQL compare-and-set; do not replace with JSON files.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any

from backend.order_engine import BadOrder

class SqliteOrders:
    def __init__(self,db_path:str|Path,*,preview_path:str|Path|None=None):
        self.path=Path(db_path).expanduser()
        self.preview_path=Path(preview_path).expanduser() if preview_path else None
        if self.path.is_symlink():
            raise BadOrder("Refusing database symlink")
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=RLock()
        existed=self.path.exists()
        # chmod restricts permissions even with an unsafe caller umask.
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS offers
                  (id TEXT PRIMARY KEY,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS orders
                  (id TEXT PRIMARY KEY,status TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS notification_outbox
                  (event_key TEXT PRIMARY KEY,payload TEXT NOT NULL,
                   state TEXT NOT NULL DEFAULT 'PENDING',
                   created_at TEXT NOT NULL DEFAULT (datetime('now')),
                   delivered_at TEXT);
            """)
        os.chmod(self.path,0o600)
        if self.path.is_symlink() or (self.path.stat().st_mode & 0o077):
            raise BadOrder("Private SQLite permissions invalid")

    def _connect(self):
        db=sqlite3.connect(str(self.path),timeout=15,isolation_level=None)
        db.execute("PRAGMA busy_timeout=15000")
        db.execute("PRAGMA journal_mode=WAL")
        db.row_factory=sqlite3.Row
        return db

    @staticmethod
    def _serialize(value):
        return json.dumps(value,ensure_ascii=False,separators=(",",":"),sort_keys=True)

    def get_preview(self,preview_id:str)->dict[str,Any]|None:
        if self.preview_path is None or not self.preview_path.is_file():
            return None
        data=json.loads(self.preview_path.read_text(encoding="utf-8"))
        if data.get("schema")!="jamaica.tour-previews.v1" or data.get("bookable") is not False:
            return None
        return next((row for row in data.get("previews",[])
                    if isinstance(row,dict) and row.get("id")==preview_id),None)

    def save_verified_offer(self,offer:dict[str,Any])->None:
        if not isinstance(offer,dict) or not offer.get("id"):
            raise BadOrder("Invalid private quote")
        with self.lock,self._connect() as db:
            db.execute("INSERT INTO offers (id,payload) VALUES (?,?)",
                       (offer["id"],self._serialize(offer)))

    def get_offer(self,offer_id:str)->dict[str,Any]|None:
        with self.lock,self._connect() as db:
            row=db.execute("SELECT payload FROM offers WHERE id=?",(offer_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def create_order(self,order:dict[str,Any])->None:
        if not isinstance(order,dict) or not order.get("id") or not order.get("status"):
            raise BadOrder("Missing order ID or status")
        with self.lock,self._connect() as db:
            db.execute("INSERT INTO orders (id,status,payload) VALUES (?,?,?)",
                       (order["id"],order["status"],self._serialize(order)))

    def get_order(self,order_id:str)->dict[str,Any]|None:
        with self.lock,self._connect() as db:
            row=db.execute("SELECT payload FROM orders WHERE id=?",(order_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def transition(self,order_id:str,expected_status:str,new_status:str,
                   updates:dict[str,Any])->bool:
        if (not isinstance(updates,dict) or not expected_status or not new_status or
            "id" in updates or "status" in updates):
            raise BadOrder("Invalid atomic transition")
        with self.lock,self._connect() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                row=db.execute("SELECT payload,status FROM orders WHERE id=?",
                               (order_id,)).fetchone()
                if row is None or row["status"]!=expected_status:
                    db.execute("ROLLBACK")
                    return False
                obj=json.loads(row["payload"])
                obj.update(updates)
                obj["status"]=new_status
                updated=db.execute(
                    "UPDATE orders SET status=?,payload=? WHERE id=? AND status=?",
                    (new_status,self._serialize(obj),order_id,expected_status))
                if updated.rowcount!=1:
                    db.execute("ROLLBACK")
                    return False
                db.execute("COMMIT")
                return True
            except Exception:
                db.execute("ROLLBACK")
                raise

    def enqueue_once(self,key:str,event:dict[str,Any])->None:
        if not isinstance(key,str) or not key or not isinstance(event,dict):
            raise BadOrder("Invalid notification event")
        with self.lock,self._connect() as db:
            db.execute("INSERT OR IGNORE INTO notification_outbox(event_key,payload) VALUES (?,?)",
                       (key,self._serialize(event)))

    def pending_events(self,limit:int=20):
        if type(limit) is not int or not 1<=limit<=100:
            raise BadOrder("Outbox limit invalid")
        with self.lock,self._connect() as db:
            rows=db.execute("SELECT event_key,payload FROM notification_outbox "
                            "WHERE state='PENDING' ORDER BY created_at,event_key LIMIT ?",
                            (limit,)).fetchall()
        return [(r["event_key"],json.loads(r["payload"])) for r in rows]

    def mark_delivered(self,key:str)->None:
        with self.lock,self._connect() as db:
            db.execute("UPDATE notification_outbox SET state='SENT', "
                       "delivered_at=datetime('now') WHERE event_key=? AND state='PENDING'",(key,))

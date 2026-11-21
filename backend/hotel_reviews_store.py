"""JAMAICA private, moderated traveler review storage.

This module is a durable backend, not a static GitHub Pages form.
Only approved reviews can be read publicly. Submissions are NEVER published
without a separate owner action. Names are unverified pseudonyms, not evidence
of a completed stay. No passport, financial data or raw IP is retained.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

RE_ID=re.compile(r"^\d{7,20}$")
RE_MONTH=re.compile(r"^(20\d{2})-(0[1-9]|1[0-2])$")
RE_URL=re.compile(r"(?:https?://|www\.)",re.I)
MAX_REVIEW=2500

class ReviewError(ValueError):
    pass

def clean_text(text,minimum:int,maximum:int):
    if not isinstance(text,str):
        raise ReviewError("INVALID_TEXT")
    text=unicodedata.normalize("NFC",text).strip()
    if not minimum<=len(text)<=maximum:
        raise ReviewError("INVALID_TEXT_LENGTH")
    if any(ord(ch)<32 and ch not in ("\n","\t") for ch in text):
        raise ReviewError("INVALID_CONTROL_CHAR")
    if "<" in text or ">" in text or RE_URL.search(text):
        raise ReviewError("NO_HTML_OR_LINKS")
    return text

def validate(body):
    if not isinstance(body,dict):
        raise ReviewError("INVALID_REVIEW_BODY")
    if body.get("website") or body.get("consent") is not True:
        raise ReviewError("CONSENT_OR_HONEYPOT")
    hotel_id=body.get("hotel_id")
    if not isinstance(hotel_id,str) or not RE_ID.fullmatch(hotel_id):
        raise ReviewError("INVALID_HOTEL")
    rating=body.get("rating")
    if type(rating) is not int or not 1<=rating<=5:
        raise ReviewError("INVALID_RATING")
    month=body.get("visit_month")
    if month in ("",None):
        month=None
    elif not isinstance(month,str) or not RE_MONTH.fullmatch(month):
        raise ReviewError("INVALID_VISIT_MONTH")
    else:
        if month > datetime.now(timezone.utc).strftime("%Y-%m"):
            raise ReviewError("FUTURE_REVIEW_MONTH")
    return {"hotel_id":hotel_id,"display_name":clean_text(body.get("display_name"),2,60),
            "rating":rating,"text":clean_text(body.get("text"),40,MAX_REVIEW),
            "visit_month":month}

class HotelReviews:
    def __init__(self,db_path,hotel_directory,secret):
        self.db_path=Path(db_path).expanduser()
        self.catalog_path=Path(hotel_directory).expanduser()
        if not isinstance(secret,str) or len(secret)<32:
            raise ReviewError("SECRET_REQUIRED")
        if self.db_path.is_symlink():
            raise ReviewError("DB_SYMLINK_FORBIDDEN")
        self.secret=secret.encode("utf-8")
        self.db_path.parent.mkdir(parents=True,exist_ok=True)
        self.db_path.parent.chmod(0o700)
        with self._db() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS hotel_reviews(
                id TEXT PRIMARY KEY,
                hotel_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
                review_text TEXT NOT NULL,
                visit_month TEXT,
                status TEXT NOT NULL CHECK(status IN ('PENDING','APPROVED','REJECTED')),
                created_at TEXT NOT NULL,
                moderated_at TEXT,
                moderation_note TEXT,
                actor_digest TEXT NOT NULL
              );
              CREATE INDEX IF NOT EXISTS hotel_reviews_hotel_status
                ON hotel_reviews(hotel_id,status,created_at);
              CREATE INDEX IF NOT EXISTS hotel_reviews_actor_time
                ON hotel_reviews(actor_digest,created_at);
            """)
        os.chmod(self.db_path,0o600)

    @contextmanager
    def _db(self):
        conn=sqlite3.connect(str(self.db_path),timeout=12)
        conn.row_factory=sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def hotel_exists(self,hotel_id):
        if not isinstance(hotel_id,str) or not RE_ID.fullmatch(hotel_id):
            return False
        try:
            data=json.loads(self.catalog_path.read_text(encoding="utf-8"))
            return (data.get("schema")=="jamaica.destination-directory.v1" and
                    any(h.get("id")==hotel_id for h in data.get("hotels",[])))
        except (OSError,ValueError):
            return False

    def _actor(self,client_ip):
        if not isinstance(client_ip,str) or not 3<=len(client_ip)<=90:
            raise ReviewError("INVALID_SUBMISSION_SOURCE")
        return hmac.new(self.secret,client_ip.encode("utf-8"),hashlib.sha256).hexdigest()

    def submit(self,body,client_ip):
        record=validate(body)
        if not self.hotel_exists(record["hotel_id"]):
            raise ReviewError("HOTEL_NOT_FOUND")
        actor=self._actor(client_ip)
        created=datetime.now(timezone.utc).isoformat(timespec="seconds")
        since=datetime.now(timezone.utc).timestamp()-24*3600
        review_id=secrets.token_hex(16)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            recent=db.execute("SELECT created_at FROM hotel_reviews WHERE actor_digest=?",
                              (actor,)).fetchall()
            recent_count=0
            for item in recent:
                try:
                    if datetime.fromisoformat(item["created_at"]).timestamp()>since:
                        recent_count+=1
                except (TypeError,ValueError):
                    continue
            if recent_count>=3:
                raise ReviewError("TOO_MANY_REVIEWS")
            db.execute("""INSERT INTO hotel_reviews
                   (id,hotel_id,display_name,rating,review_text,visit_month,
                    status,created_at,actor_digest)
                   VALUES (?,?,?,?,?,?,'PENDING',?,?)""",
                (review_id,record["hotel_id"],record["display_name"],
                 record["rating"],record["text"],record["visit_month"],created,actor))
        return {"status":"PENDING_MODERATION"}

    def public(self,hotel_id,limit=30):
        if not self.hotel_exists(hotel_id):
            raise ReviewError("HOTEL_NOT_FOUND")
        if type(limit) is not int or not 1<=limit<=60:
            raise ReviewError("INVALID_LIMIT")
        with self._db() as db:
            rows=db.execute("""SELECT id,display_name,rating,review_text,
                   visit_month,created_at FROM hotel_reviews
                   WHERE hotel_id=? AND status='APPROVED'
                   ORDER BY created_at DESC LIMIT ?""",(hotel_id,limit)).fetchall()
        return [{"id":r["id"],"display_name":r["display_name"],
                 "rating":r["rating"],"text":r["review_text"],
                 "visit_month":r["visit_month"],"created_at":r["created_at"],
                 "stay_verified":False} for r in rows]

    def pending(self,limit=50):
        with self._db() as db:
            rows=db.execute("""SELECT id,hotel_id,display_name,rating,review_text,
                   visit_month,created_at FROM hotel_reviews
                   WHERE status='PENDING' ORDER BY created_at ASC LIMIT ?""",
                   (min(max(1,limit),100),)).fetchall()
        return [dict(r) for r in rows]

    def moderate(self,review_id,approve,reason=""):
        if not isinstance(review_id,str) or not re.fullmatch(r"[a-f0-9]{32}",review_id):
            raise ReviewError("INVALID_REVIEW_ID")
        status="APPROVED" if approve else "REJECTED"
        with self._db() as db:
            cursor=db.execute("""UPDATE hotel_reviews
                SET status=?,moderated_at=?,moderation_note=?
                WHERE id=? AND status='PENDING'""",
                (status,datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 str(reason)[:200],review_id))
        return cursor.rowcount==1

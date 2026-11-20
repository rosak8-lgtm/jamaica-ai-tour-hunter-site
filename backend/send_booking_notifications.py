"""JAMAICA private booking notification dispatcher.

Only consumes durable server-side outbox after authoritative booking state.
Token and owner chat ID come from PRIVATE environment, never public git.
Delivery is at least once; the order ID allows recipients to identify repeats.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

from backend.sqlite_order_repository import SqliteOrders

TYPES={
 "TOUR_BOOKED":"✅ JAMAICA: тур забронирован и подтверждён",
 "TOUR_REQUESTED_WAITING_HOTEL":"🕒 JAMAICA: заявка оформлена, гостиница под запрос",
 "REFUND_REQUIRED":"⚠️ JAMAICA: требуется проверить возврат оплаты",
}

def format_event(event:dict)->str:
    if not isinstance(event,dict) or event.get("type") not in TYPES:
        raise ValueError("Unsupported notification event")
    order_id=str(event.get("order_id",""))
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}",order_id):
        raise ValueError("Invalid order reference")
    result=TYPES[event["type"]]+"\nЗаказ: "+order_id
    booking=str(event.get("supplier_booking_id",""))
    if booking and re.fullmatch(r"[A-Za-z0-9_-]{3,100}",booking):
        result+="\nНомер заявки: "+booking
    return result

def deliver(db:SqliteOrders,sender,limit=20)->int:
    delivered=0
    for key,event in db.pending_events(limit):
        try:
            sender(format_event(event))
        except Exception:
            break  # Keep durable event for later retry.
        db.mark_delivered(key)
        delivered+=1
    return delivered

def telegram_sender(token:str,chat_id:str):
    if (not re.fullmatch(r"[0-9]{5,15}:[A-Za-z0-9_-]{20,160}",token) or
        not re.fullmatch(r"-?[0-9]{5,20}",chat_id)):
        raise ValueError("Private Telegram credentials not configured")
    url="https://api.telegram.org/bot"+token+"/sendMessage"
    def send(message:str):
        body=urllib.parse.urlencode({"chat_id":chat_id,"text":message,
                                     "disable_web_page_preview":"true"}).encode()
        request=urllib.request.Request(url,data=body,method="POST",
                                       headers={"Content-Type":"application/x-www-form-urlencoded"})
        with urllib.request.urlopen(request,timeout=20) as response:
            data=json.loads(response.read(4096))
            if response.status!=200 or data.get("ok") is not True:
                raise RuntimeError("Telegram did not confirm message delivery")
    return send

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    p.add_argument("--send",action="store_true",
                   help="Deliver existing outbox events with private credentials")
    args=p.parse_args()
    db=SqliteOrders(Path(args.db))
    pending=len(db.pending_events(100))
    if not args.send:
        print("JAMAICA_OUTBOX_READONLY_PENDING="+str(pending))
        return
    token=os.getenv("JAMAICA_TELEGRAM_BOT_TOKEN","")
    chat=os.getenv("JAMAICA_TELEGRAM_OWNER_CHAT_ID","")
    send=telegram_sender(token,chat)
    print("JAMAICA_TELEGRAM_NOTIFICATIONS_SENT="+str(deliver(db,send)))
if __name__=="__main__":
    main()

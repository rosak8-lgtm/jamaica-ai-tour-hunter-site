#!/usr/bin/env python3
"""Probe the documented price-list discovery endpoint, without credentials or booking.
Never treats a minprice or route listing as a verified total tour quote.
"""
import gzip, json, urllib.request, urllib.error
from urllib.parse import urlencode
u="https://export.bgoperator.ru/yandex?"+urlencode({
 "action":"files","flt":"100410000051","flt2":"100510397223","xml":"11"
})
request=urllib.request.Request(u,headers={"Accept-Encoding":"gzip","User-Agent":"JAMAICA-readonly-price-catalog/1.0"})
try:
 with urllib.request.urlopen(request,timeout=22) as r:
  raw=r.read(12_000_001)
  if len(raw)>12_000_000:raise ValueError("RESPONSE_TOO_LARGE")
  if r.headers.get("Content-Encoding","").lower()=="gzip":raw=gzip.decompress(raw)
  data=json.loads(raw)
  arr=data.get("entries",[]) if isinstance(data,dict) else []
  print("OFFICIAL_PRICE_LIST_HTTP="+str(r.status))
  print("BG_PRICE_LIST_ENTRIES="+str(len(arr)))
  print("BG_PRICE_LIST_KEYS="+",".join(sorted(list(arr[0].keys()))[:24]) if arr else "BG_PRICE_LIST_KEYS=NONE")
  print("PRICE_LIST_IS_NOT_A_BOOKABLE_QUOTE=YES")
except urllib.error.HTTPError as e:
 print("BG_PRICE_LIST_HTTP="+str(e.code))
 print("OFFICIAL_PRICE_LIST_AUTH_REQUIRED="+str(e.code in (401,403)).upper())
except Exception as e:
 print("BG_PRICE_LIST_FETCH_UNVERIFIED="+type(e).__name__)

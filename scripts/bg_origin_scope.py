"""Explicit city/country scope for the future shared multi-origin worker.
No network, no publication permission. Legacy Irkutsk identity is unchanged.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from urllib.parse import urlencode

IRKUTSK_ID="100510397223"
ID=re.compile(r"[0-9]{7,20}\Z")

@dataclass(frozen=True)
class Scope:
    origin_id: str
    origin: str
    country_id: str
    country: str

    def __post_init__(self):
        for value in (self.origin_id,self.country_id):
            if not isinstance(value,str) or not ID.fullmatch(value):
                raise ValueError("INVALID_SCOPE_ID")
        for value in (self.origin,self.country):
            if not isinstance(value,str) or not 2<=len(value)<=100 or any(c in value for c in "<>{}|") or any(ord(c)<32 for c in value):
                raise ValueError("INVALID_SCOPE_NAME")
        if (self.origin_id==IRKUTSK_ID)!=(self.origin=="Иркутск"):
            raise ValueError("IRKUTSK_IDENTITY")

    @classmethod
    def from_registry(cls,registry,origin_id,country_id):
        if registry.get("schema")!="jamaica.origin-registry.v1" or registry.get("classification")!="SEARCH_SCOPE_ONLY_NOT_OFFERS":
            raise ValueError("REGISTRY_SCHEMA")
        cities=registry.get("cities",{})
        countries=registry.get("countries",{})
        matches=[p for p in registry.get("pairs",[]) if p.get("origin_id")==origin_id and p.get("country_id")==country_id]
        if len(matches)!=1:
            raise ValueError("SCOPE_NOT_UNIQUE")
        p=matches[0]
        if p.get("origin")!=cities.get(origin_id) or p.get("country")!=countries.get(country_id):
            raise ValueError("SCOPE_DIRECTORY_MISMATCH")
        return cls(origin_id,p["origin"],country_id,p["country"])

    def files_query(self):
        return urlencode({"action":"files","flt":self.country_id,"flt2":self.origin_id,"xml":"11"})

    def preview_id(self,hotel_id,day,nights,room):
        legacy="|".join((self.country,hotel_id,day,str(nights),room))
        key=legacy if self.origin_id==IRKUTSK_ID else json.dumps(
            ["jamaica.origin.v2",self.origin_id,self.country,hotel_id,day,nights,room],
            ensure_ascii=False,separators=(",",":"))
        return "p_"+sha256(key.encode()).hexdigest()[:24]

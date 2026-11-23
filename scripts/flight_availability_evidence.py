"""Read-only flight availability EVIDENCE from official BG extended JSON.

BG docs: tourComposition flight n=0 outbound / n=1 return; q[0] describes
economy availability (1-9, a=many), 0=request, c=none. q[1] concerns
business class. The undocumented r marker is NOT proof of free seats.
Unknown/ambiguous means NOT VERIFIED.

This is not a booking hold. Must independently recheck both flights before
payment and again after payment before creating an agency application.
"""
from __future__ import annotations

def economy_q_available(q)->bool:
    if not isinstance(q,str) or len(q)!=2:
        return False
    if q[0] not in "123456789a":
        return False
    return q[1] in "0123456789ac"

def flight_pair_evidence(entry:dict)->dict:
    result={"out_green":False,"back_green":False,"both_green":False,
            "status":"UNVERIFIED"}
    if not isinstance(entry,dict):
        return result
    if entry.get("isstop") or entry.get("stop"):
        return {**result,"status":"STOP_SALE"}
    if not isinstance(entry.get("tourComposition"),list):
        return result
    by_direction={0:[],1:[]}
    for part in entry["tourComposition"]:
        if not isinstance(part,dict) or part.get("type")!="flight":
            continue
        n=part.get("n")
        if n in (0,"0"):by_direction[0].append(part)
        if n in (1,"1"):by_direction[1].append(part)
    if len(by_direction[0])!=1 or len(by_direction[1])!=1:
        return result
    outbound,back=by_direction[0][0],by_direction[1][0]
    if not outbound.get("id") or not back.get("id"):
        return result
    a=economy_q_available(outbound.get("q"))
    b=economy_q_available(back.get("q"))
    if a and b:status="BOTH_AVAILABLE_AT_SNAPSHOT"
    elif a or b:status="ONLY_ONE_SIDE_AVAILABLE"
    else:status="NOT_CONFIRMED"
    return {"out_green":a,"back_green":b,"both_green":a and b,"status":status}

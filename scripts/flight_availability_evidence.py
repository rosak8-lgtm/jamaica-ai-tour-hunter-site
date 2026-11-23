"""Read-only flight availability EVIDENCE from official BG extended JSON.

BG docs: tourComposition flight n=0 outbound / n=1 return; q[0] describes
economy availability (1-9, a=many), 0=request, c=none. q[1] concerns
business class. BG also DOCUMENTS "r" for a regular Aeroflot service with
up-to-date prices/seat information, but the marker itself does not specify
a positive number of open economy seats. Keep "r" non-green until an
independent provider seat/quote check proves actual availability.
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

def economy_q_reason(q)->str:
    """Non-sensitive aggregate reason only; never return provider IDs or raw q.

    Documented "r" means regular flight, NOT a numerical green seat count.
    Restrict the second (business-class) marker to the published alphabet.
    """
    if economy_q_available(q):
        return "GREEN"
    if q == "0":
        return "ON_REQUEST"
    if not isinstance(q,str) or len(q)!=2 or q[1] not in "0123456789acr":
        return "UNKNOWN"
    if q[0]=="0":
        return "ON_REQUEST"
    if q[0]=="c":
        return "SOLD_OUT"
    if q[0]=="r":
        return "REGULAR_NOT_SEAT_VERIFIED"
    return "UNKNOWN"


def flight_pair_reasons(entry:dict)->tuple[str,str]:
    """Summarize economy status of exactly one outbound and one return."""
    if not isinstance(entry,dict) or entry.get("stop") or entry.get("isstop"):
        return "UNKNOWN","UNKNOWN"
    composition=entry.get("tourComposition")
    if not isinstance(composition,list):
        return "UNKNOWN","UNKNOWN"
    legs={0:[],1:[]}
    for part in composition:
        if not isinstance(part,dict) or part.get("type")!="flight":
            continue
        n=part.get("n")
        if n in (0,"0"):
            legs[0].append(part)
        elif n in (1,"1"):
            legs[1].append(part)
    if len(legs[0])!=1 or len(legs[1])!=1 or not all(
        p.get("id") for p in (legs[0][0],legs[1][0])
    ):
        return "UNKNOWN","UNKNOWN"
    return economy_q_reason(legs[0][0].get("q")),economy_q_reason(legs[1][0].get("q"))


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

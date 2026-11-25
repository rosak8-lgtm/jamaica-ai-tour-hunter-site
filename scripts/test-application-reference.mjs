import assert from "node:assert/strict";
import fs from "node:fs";
import "./application-reference.js";
const A=globalThis.JamaicaApplicationReference;
const now=Date.now(),stamp=new Date(now).toISOString(),day=new Date(now+86400000*7).toISOString().slice(0,10);
const row={id:"pg_"+"a".repeat(24),status:"PEGAS_APPLICATION_PRICE_REFERENCE_ONLY",
 origin:"Иркутск",country:"Турция",hotel:"TEST HOTEL",room:"DBL",resort:"TEST RESORT",
 depart_date:day,nights:7,price_reference_rub:120000,price_reference_party:"TWO_ADULTS",
 price_source:"PEGAS_OPEN_APPLICATION_MANDATORY_FEES_INCLUDED",price_observed_at_utc:stamp,
 evidence:{hotel_filter_verified:true,flight_filter_verified:true,cheapest_eligible_price_clicked:true,
 final_price_observed:true,mandatory_fees_included:true,observed_at_utc:stamp},
 bookable:false,quote_verified:false,availability_verified:false,flight_verified:false};
const feed={schema:"jamaica.pegas-reference-catalog.v1",refreshed_at_utc:stamp,bookable:false,quote_verified:false,previews:[row]};
assert.equal(A.eligible(row,now),true);
assert.equal(A.parse(feed,now).length,1);
for(const patch of [{bookable:true},{quote_verified:true},{price_reference_party:"FAMILY"},{price_reference_rub:0},{id:"p_"+"a".repeat(24)},{depart_date:"2026-02-30"},{country:"Вьетнам",nights:45},{price_observed_at_utc:new Date(now-1000).toISOString()}]){
 assert.equal(A.eligible({...row,...patch},now),false);
}
for(const key of ["hotel_filter_verified","flight_filter_verified","cheapest_eligible_price_clicked","final_price_observed","mandatory_fees_included"]){
 assert.equal(A.eligible({...row,evidence:{...row.evidence,[key]:false}},now),false);
}
assert.equal(A.eligible(row,now+900001),false);
assert.equal(A.parse({...feed,previews:[row,row]},now).length,0);
assert.equal(A.parse({...feed,refreshed_at_utc:new Date(now-31000).toISOString()},now).length,0);
assert.equal(A.parse({...feed,bookable:true},now).length,0);
assert.equal(A.parse(JSON.parse(fs.readFileSync("application-reference.json","utf8")),now).length,0);
const page=fs.readFileSync("index.html","utf8");
assert.ok(page.includes("...applicationRows.filter(x=>window.JamaicaApplicationReference.eligible(x))"));
assert.ok(page.includes("application-detail.html?id="));
assert.ok(page.includes("APPLICATION_PRICE_AND_FILTERS"));
const detail=fs.readFileSync("application-detail.html","utf8");
assert.ok(detail.includes("T.isTwoAdults(rooms)")&&detail.includes("R.eligible(selected)"));
assert.ok(!detail.includes("/v1/")&&!detail.includes("checkout.html"));
console.log("JAMAICA_V53_COMBINED_REFERENCE_POLICY_PASS");

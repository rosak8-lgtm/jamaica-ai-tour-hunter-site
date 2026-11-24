import fs from "node:fs";
import vm from "node:vm";
import assert from "node:assert/strict";

const context={Date,Map,Object,Array,Number};
vm.createContext(context);
vm.runInContext(fs.readFileSync("scripts/visual-selection.js","utf8"),context);
vm.runInContext(fs.readFileSync("scripts/public-visual-policy.js","utf8"),context);
const policy=context.JamaicaPublicVisualPolicy;
const parsed=context.JamaicaVisualSelection;
const now=Date.now(),id="p_"+"a".repeat(24),id2="p_"+"b".repeat(24);
const row={id,hotel_id:"102612345678",hotel:"ART DELUXE HOTEL",country:"Вьетнам",
 origin:"Иркутск",depart_date:new Date(now+7*86400000).toISOString().slice(0,10),
 room:"STANDARD",nights:7,resort:"Нячанг",
 status:"REFERENCE_PRICE_LIST_ONLY",price_reference_rub:137099,
 quote_verified:false,availability_verified:false,flight_verified:false,
 bookable:false};
const proof={preview_id:id,observed_at_utc:new Date(now-1000).toISOString(),
 route_best_price_seen:true,both_green_planes_seen:true};
const feed=x=>({schema:"jamaica.visual-selection.v1",entries:x,
 bookable:false,quote_verified:false,availability_verified:false});
function valid(x){return parsed.read(feed([x]),now);}
assert.equal(policy.eligible(row,new Map(),now),false,
 "Even a real supplier price is not a checked route plus two-green pair");
assert.equal(policy.eligible(row,valid(proof),now),true);
assert.equal(policy.filter([row,{...row,id:id2}],valid(proof),now).length,1,
 "Other hotels/IDs cannot inherit the same proof");
assert.equal(policy.filter([row,{...row,id:id2}],new Map(),now).length,0,
 "Empty receipts must yield ZERO public cards");
for(const bad of [
 {...proof,both_green_planes_seen:false},
 {...proof,route_best_price_seen:false},
 {...proof,preview_id:id2},
 {...proof,observed_at_utc:new Date(now-16*60000).toISOString()},
 {...proof,observed_at_utc:new Date(now+90000).toISOString()},
 {...proof,source_url:"https://example.com/private"},
 ]){
 assert.equal(policy.eligible(row,valid(bad),now),false,
 "Invalid, stale, future or wrong-tour proof must never publish a tour");
}
assert.equal(policy.eligible({...row,status:"PREVIOUSLY_SEEN_NOT_RECHECKED"},valid(proof),now),false);
assert.equal(policy.eligible({...row,bookable:true},valid(proof),now),false);
assert.equal(policy.eligible({...row,flight_verified:true},valid(proof),now),false);
assert.equal(policy.eligible({...row,depart_date:"2020-01-01"},valid(proof),now),false);
assert.equal(policy.eligible({...row,id:id2},valid(proof),now),false);
const priced={...row,price_source:"BG_EXACT_SELECTED_GREEN_BROWSER",
 price_reference_party:"TWO_ADULTS",price_observed_at_utc:proof.observed_at_utc};
assert.equal(policy.observedPrice(priced,valid(proof),now),137099);
assert.equal(policy.observedPrice({...priced,price_observed_at_utc:new Date(now-2000).toISOString()},valid(proof),now),null);
assert.equal(policy.observedPrice(priced,new Map(),now),null);
assert.equal(policy.observedPrice(priced,valid(proof),now+16*60000),null);
assert.equal(policy.observedPrice({...priced,price_reference_party:"UNVERIFIED"},valid(proof),now),null);
assert.equal(policy.observedPrice({...priced,id:id2},valid(proof),now),null);
const pages=Object.fromEntries(["index.html","preview.html","hotel.html","quote.html",
 "route.html","tour.html","checkout.html"].map(n=>[n,fs.readFileSync(n,"utf8")]));
assert.ok(pages["index.html"].includes("JamaicaPublicVisualPolicy.observedPrice(x,visualProofs)"));
assert.ok(pages["preview.html"].includes("JamaicaPublicVisualPolicy.observedPrice(p,selectedProofs)"));
assert.ok(pages["preview.html"].includes("Зафиксирована для выбранного маршрута"));
assert.ok(pages["preview.html"].includes("setInterval(expireSelection,15000)"));
for(const p of ["index.html","preview.html","hotel.html","quote.html"]){
 assert.ok(pages[p].includes("scripts/public-visual-policy.js"),p+" must load gate");
 assert.ok(pages[p].includes("JamaicaPublicVisualPolicy."),p+" must use gate");
}
assert.ok(pages["index.html"].includes('let list=verifiedRows().filter(x=>'),
 "Main results must ALWAYS enforce, not optionally select, proof");
assert.ok(pages["index.html"].includes('checked disabled aria-label="Обязательное условие'),
 "Visual proof checkbox must not be uncheckable to reveal prohibited cards");
assert.ok(!pages["index.html"].includes('if($("visualProofOnly").checked)list='),
 "No user bypass for unverified previews");
assert.ok(pages["preview.html"].includes("if(!selectedProofs.has(id))"),
 "Direct tour details cannot bypass exact proof");
assert.ok(pages["quote.html"].includes("if(!proofs.has(id))")&&
 pages["quote.html"].includes("const currentProofs=await"),
 "Direct quote and click must both recheck proof");
assert.ok(pages["hotel.html"].includes("JamaicaPublicVisualPolicy.filter(all,proofs)"),
 "No unverified room/date cards in hotel details");
for(const p of ["index.html","tour.html","checkout.html"]){
 assert.ok(pages[p].includes('o.sale_policy!=="BG_BEST_PRICE_TWO_FLIGHTS"'),
  p+" must never accept two-green-only offers without best price");
 assert.ok(!pages[p].includes('o.sale_policy==="STANDARD_TWO_FLIGHTS"'),
  p+" must reject non-best-price offers");
}
console.log("JAMAICA_STRICT_BEST_PRICE_BOTH_GREEN_ALL_PUBLIC_TOUR_CARDS_PASS");

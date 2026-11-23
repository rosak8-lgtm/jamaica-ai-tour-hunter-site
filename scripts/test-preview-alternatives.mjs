import fs from "node:fs";
import vm from "node:vm";
import assert from "node:assert/strict";
const code=fs.readFileSync("scripts/preview-alternatives.js","utf8");
new vm.Script(code,{filename:"preview-alternatives.js"});
const context={window:{},Date};
vm.runInNewContext(code,context);
const pick=context.window.JamaicaPreviewAlternatives;
const TODAY="2026-11-23";
function x(id,country,hotel,depart,opts={}){
 return {id:"p_"+id.toString(16).padStart(24,"0"),
   hotel_id:String(hotel).padStart(12,"0"),hotel:"TEST HOTEL "+hotel,
   country,resort:opts.resort||"TEST RESORT",origin:"Иркутск",
   depart_date:depart,nights:opts.nights||7,room:"STANDARD",
   status:"REFERENCE_PRICE_LIST_ONLY",
   price_reference_rub:90000,price_reference_party:"TWO_ADULTS",
   quote_verified:false,flight_verified:false,
   availability_verified:false,bookable:false,...opts};
}
const selected=x(1,"Таиланд",101,"2026-12-12");
const rows=[selected];
for(let i=0;i<100;i++)rows.push(x(100+i,"Таиланд",101,"2026-12-13"));
rows.push(x(2,"Таиланд",101,"2026-12-11"));
rows.push(x(3,"Таиланд",102,"2026-12-12"));
rows.push(x(4,"Таиланд",103,"2026-12-14",{resort:"ДРУГОЙ КУРОРТ"}));
rows.push(x(5,"Вьетнам",104,"2026-12-12"));
rows.push(x(6,"Китай",105,"2026-12-13"));
rows.push(x(7,"Индонезия",106,"2026-12-14"));
rows.push(x(8,"Турция",107,"2026-12-15"));
rows.push(x(9,"Египет",108,"2026-12-16"));
const selectedOffers=pick.choose(rows,selected,{today:TODAY});
assert.ok(selectedOffers.length<=12);
assert.equal(new Set(selectedOffers.map(r=>r.row.id)).size,selectedOffers.length);
assert.ok(selectedOffers.every(r=>r.row.id!==selected.id));
assert.ok(selectedOffers.some(r=>r.kind==="sameHotel"));
assert.ok(selectedOffers.some(r=>r.kind==="sameResort"));
assert.ok(selectedOffers.some(r=>r.kind==="sameCountry"));
assert.ok(new Set(selectedOffers.filter(r=>r.kind==="otherCountry")
                         .map(r=>r.row.country)).size>=3,
 "The detail page must offer other real source countries, not 12 same-hotel duplicates");
assert.equal(selectedOffers[0].row.id,x(2,"Таиланд",101,"2026-12-11").id,
 "Nearest other date in the same hotel should appear first");
const invalid=[
 x(200,"Греция",200,"2026-11-01"),
 x(201,"Греция",201,"2026-12-12",{quote_verified:true}),
 x(202,"Греция",202,"2026-12-12",{origin:"Москва"}),
 x(203,"Греция",203,"2026-12-12",{bookable:true}),
 x(204,"Греция",204,"2026-12-12",{status:"PREVIOUSLY_SEEN_NOT_RECHECKED"}),
 x(205,"Греция",205,"2026-12-12",{status:"UNRECOGNIZED_SOURCE"}),
];
assert.equal(pick.choose([selected,...invalid],selected,{today:TODAY}).length,0,
 "Expired, invented availability, wrong origin, stale price and unknown source rejected");
const old=x(300,"Китай",306,"2026-12-12",{
 status:"PREVIOUSLY_SEEN_NOT_RECHECKED",
 price_reference_rub:null,price_reference_party:"UNVERIFIED"});
assert.equal(pick.choose([selected,old],selected,{today:TODAY})[0].row.price_reference_rub,null);
assert.equal(pick.choose([selected,old],selected,{today:TODAY})[0].kind,"otherCountry");
assert.equal(pick.choose([],selected,{today:TODAY}).length,0);
console.log("JAMAICA_REAL_COUNTRY_SHARD_ALTERNATIVES=PASS");

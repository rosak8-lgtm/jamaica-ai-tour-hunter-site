import fs from "node:fs";
import vm from "node:vm";
import assert from "node:assert/strict";
const ctx={};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync("scripts/source-coverage.js","utf8"),ctx);
const parse=ctx.JamaicaSourceCoverage.parse;
const old={schema:"jamaica.tour-previews.v1",previews:[],
 countries_status:[
  {country:"Вьетнам",previews:33,sampled_departure_months:["2026-12","2027-01"]},
  {country:"Таиланд",previews:18,sampled_departure_months:["2026-12","bogus"]},
  {country:"Китай",previews:0},
  {country:"Мальдивы",previews:3}
 ]};
assert.deepEqual(Array.from(parse(old),x=>x.country),
 ["Таиланд","Вьетнам","Мальдивы"]);
assert.equal(parse(old)[0].source_rows_observed,18);
assert.deepEqual(Array.from(parse(old)[1].sampled_departure_months),
 ["2026-12","2027-01"]);
const strict={schema:"jamaica.tour-previews.v1",previews:[],
 publication_rule:"BG_ROUTE_FIRST_BEST_PRICE_BOTH_GREEN_V1",
 search_coverage:{classification:"SOURCE_SCAN_ONLY_NOT_OFFERS",countries:[
 {country:"Таиланд",source_rows_observed:500,sampled_departure_months:["2026-12","2027-01"]},
 {country:"Китай",source_rows_observed:300,sampled_departure_months:["2027-02"]}
 ]},
 countries_status:[{country:"Таиланд",previews:0},{country:"Китай",previews:0}]};
assert.deepEqual(Array.from(parse(strict),x=>x.country),["Таиланд","Китай"],
 "Strict zero-card publication must retain actual search geography");
assert.equal(parse(strict)[0].source_rows_observed,500);
for(const bad of [
 null,{}, {...old,countries_status:new Array(121).fill({country:"Китай",previews:1})},
 {...old,countries_status:[{country:"<script>",previews:4}]},
 {...old,countries_status:[{country:"Таиланд",previews:1},{country:"Таиланд",previews:1}]},
])assert.equal(parse(bad).length,0);
const index=fs.readFileSync("index.html","utf8");
const css=fs.readFileSync("assets/jamaica-search-ui.css","utf8");
assert.ok(index.includes('id="sourceSearchCoverage"')&&
 index.includes("JamaicaSourceCoverage.parse(data)")&&
 index.includes('renderSourceScanCoverage();')&&
 index.includes('checked disabled aria-label="Обязательное условие'),
 "Actual source geography should appear only as non-commercial metadata, never a tour");
assert.ok(index.includes('id="sourceSearchCountryChips"')&&
 index.includes('class="offerCards" id="previewCards"')&&
 index.includes('let list=verifiedRows().filter(x=>')&&
 !index.includes('let list=previewRecords.filter(x=>'),
 "Preview cards must remain protected by visual policy");
assert.ok(css.includes(".sourceSearchCoverage")&&
 css.includes(".sourceSearchChip")&&
 css.includes("@media(max-width:580px)"),
 "Scanning geography must have an accessible mobile experience");
console.log("JAMAICA_NONCOMMERCIAL_SEARCH_COVERAGE_WITH_ZERO_VERIFIED_TOURS_PASS");

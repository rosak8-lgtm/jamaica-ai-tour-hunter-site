import fs from "node:fs";
import vm from "node:vm";
import assert from "node:assert/strict";
const src=fs.readFileSync("scripts/month-offer-filters.js","utf8");
new vm.Script(src);
const ctx={window:{}};vm.runInNewContext(src,ctx);
const {range,activeMonth,monthsFor,observedMonthsFor}=ctx.window.JamaicaMonths;
assert.equal(range("2026-12").from,"2026-12-01");
assert.equal(range("2026-12").to,"2026-12-31");
assert.equal(range("2027-02").to,"2027-02-28");
assert.equal(range("2028-02").to,"2028-02-29");
assert.equal(range("2099-12").to,"2099-12-31");
for(const x of ["1999-12","2027-13","2027-00","2027-2","2077-04-x",null]){
 assert.equal(range(x),null);
}
assert.equal(activeMonth("2026-12-01","2026-12-31"),"2026-12");
assert.equal(activeMonth("2027-02-01","2027-02-28"),"2027-02");
assert.equal(activeMonth("2027-01-10","2027-01-31"),null,
 "Custom date windows are not whole-month filters");
assert.equal(activeMonth("2027-01-01","2027-02-28"),null);
const row=(country,date,origin="Иркутск")=>({
 country,origin,depart_date:date,bookable:false});
const data=[
 row("Таиланд","2026-12-01"),
 row("Таиланд","2026-12-24"),
 row("Таиланд","2027-01-05"),
 row("Китай","2027-01-20"),
 row("Вьетнам","2027-02-12"),
 row("Вьетнам","2027-03-14"),
 row("Вьетнам","2027-03-22","Москва"),
 row("Китай","2026-11-10"),
 row("Таиланд","2027-02-30"),
 row("Филиппины","2027-12-99"),
];
const all=monthsFor(data,{origin:"иркутск",today:"2026-11-23"});
assert.deepEqual(Array.from(all.keys()),
 ["2026-12","2027-01","2027-02","2027-03"]);
assert.equal(all.get("2026-12"),2);
assert.equal(all.get("2027-01"),2);
assert.equal(all.get("2027-02"),1);
assert.equal(all.get("2027-03"),1);
const filtered=monthsFor(data,{
 origin:"ИРКУТСК",country:"таиланд",today:"2026-11-23"});
assert.deepEqual(Array.from(filtered,([month,count])=>[month,count]),
 [["2026-12",2],["2027-01",1]]);
assert.equal(monthsFor(data,{
 origin:"Новосибирск",today:"2026-11-23"}).size,0);
assert.equal(monthsFor(data,{origin:"Москва",today:"2026-11-23"}).get("2027-03"),1);
assert.equal(monthsFor(data,{origin:"Иркутск",country:"Япония"}).size,0);
assert.equal(monthsFor(null,{origin:"Иркутск"}).size,0);
// V101: no supplier claims from source metadata; never transfer another city's calendar.
const coverage=[{country:"Таиланд",sampled_departure_months:["2026-10","2026-12","2027-01","2027-13","2027-01"]},
 {country:"Китай",sampled_departure_months:["2027-02"]},{country:"Вьетнам",sampled_departure_months:null}];
const observed=(q)=>Array.from(observedMonthsFor(coverage,q));
assert.deepEqual(observed({origin:"Иркутск",today:"2026-11-27"}),["2026-12","2027-01","2027-02"]);
assert.deepEqual(observed({origin:"ИРКУТСК",country:"таиланд",today:"2026-11-27"}),["2026-12","2027-01"]);
assert.deepEqual(observed({origin:"Новосибирск",today:"2026-11-27"}),[]);
assert.deepEqual(observed({origin:"Иркутск",country:"Египет",today:"2026-11-27"}),[]);
assert.deepEqual(observed({origin:"Иркутск",country:"Вьетнам",today:"2026-11-27"}),[]);
assert.deepEqual(Array.from(observedMonthsFor(null,{origin:"Иркутск"})),[]);
assert.deepEqual(observed({origin:"Иркутск",today:"2027-01-31"}),["2027-01","2027-02"]);
assert.equal(coverage[0].sampled_departure_months.length,5);
const page=fs.readFileSync("index.html","utf8");
const css=fs.readFileSync("assets/jamaica-search-ui.css","utf8");
assert.ok(page.includes('id="quickMonths"')&&
 page.includes('./scripts/month-offer-filters.js')&&
 page.includes('renderMonthShortcuts()')&&
 page.includes('const dates=month?window.JamaicaMonths.range(month):null')&&
 page.includes('form.requestSubmit()'),
 "Month choices must be wired to the real search");
assert.ok(css.includes('.quickMonthChip[aria-pressed="true"]')&&
 css.includes('.quickMonthChips{display:flex'),
 "Month chips must be accessible and mobile scrollable");
assert.ok(page.includes('id="observedMonthChoices"')&&page.includes('months.filter(month=>!fresh.has(month))')&&
 page.includes('Это фильтр каталога, не заявка оператору')&&page.includes('dateOptions.length.toLocaleString("ru-RU")'));
console.log("JAMAICA_REAL_PUBLISHED_MONTH_SHORTCUTS_PASS");
console.log("JAMAICA_V101_OBSERVED_CALENDAR_PASS");

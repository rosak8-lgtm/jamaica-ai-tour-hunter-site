import assert from "node:assert/strict";
import "./search-recovery.js";
const {analyze,departures,otherCountryOptions,dateOptions,otherCities}=globalThis.JamaicaSearchRecovery;
const row=(origin,country,depart_date,nights)=>({origin,country,depart_date,nights});
const rows=[row("Иркутск","Китай","2026-12-04",5),row("Иркутск","Китай","2026-12-15",9),row("Иркутск","Вьетнам","2026-12-04",9),row("Москва","Китай","2026-12-04",9)];
const q={origin:"Иркутск",country:"Китай",from:"2026-12-02",to:"2026-12-10",nights:[7,9,10]};
const a=analyze(rows,q);
assert.deepEqual([a.city,a.country,a.dates,a.nights],[3,2,1,0]);
assert.deepEqual(a.durations,[5]);
assert.deepEqual(a.alternatives.map(x=>[x.key,x.count]),[["nights",1],["dates",1],["both",2],["countries",1]]);
assert.equal(analyze(rows,{...q,country:"Вьетнам"}).nights,1);
assert.equal(analyze(rows,{...q,origin:"Красноярск"}).alternatives.length,0);
assert.equal(analyze(rows,q,()=>false).alternatives.length,0);
assert.equal(analyze(rows,{...q,nights:[]}).nights,1);
console.log("JAMAICA_SEARCH_RECOVERY_CITY_DATE_MULTI_NIGHT_PASS");

const opts=departures(rows,q);
assert.deepEqual(opts.map(x=>[x.country,x.date,x.count,x.nights]),[["Китай","2026-12-15",1,[9]],["Вьетнам","2026-12-04",1,[9]]]);
assert.equal(departures(rows,{...q,allowOtherCountries:false}).length,1);
assert.equal(departures(rows,q,()=>false).length,0);
assert.equal(departures(rows,{...q,origin:"Красноярск"}).length,0);
assert.equal(departures(rows,{...q,nights:[7]}).length,0);
assert.equal(departures(rows,{...q,nights:[]})[0].date,"2026-12-15");
console.log("JAMAICA_EXACT_DEPARTURE_ALTERNATIVES_PASS");

const sample=[...rows,row("Иркутск","Таиланд","2026-12-12",7),row("Иркутск","Таиланд","2026-12-05",4),row("Иркутск","Индия","2026-12-05",4),row("Москва","Египет","2026-12-05",7)];
const alternatives=otherCountryOptions(sample,q);
assert.deepEqual(alternatives.map(x=>[x.country,x.date,x.nights,x.changeDates,x.changeNights]),[["Вьетнам","2026-12-04",[9],false,false],["Таиланд","2026-12-12",[7],true,false],["Индия","2026-12-05",[4],false,true]]);
assert.equal(otherCountryOptions(sample,{...q,allowOtherCountries:false}).length,0);
assert.equal(otherCountryOptions(sample,q,()=>false).length,0);
assert.equal(otherCountryOptions(sample,{...q,origin:"Красноярск"}).length,0);
assert.equal(otherCountryOptions(sample,{...q,country:""}).length,0);
assert.equal(otherCountryOptions([...sample, row("Иркутск","Вьетнам","2026-12-04",9),row("Иркутск","Вьетнам","2026-12-04",4)],q)[0].count,2);
console.log("JAMAICA_OTHER_COUNTRY_CONCRETE_OPTIONS_PASS");

const dates=dateOptions(rows,q);
assert.deepEqual(dates.map(x=>[x.date,x.nights,x.count,x.changeDates,x.changeNights]),[["2026-12-15",[9],1,true,false],["2026-12-04",[5],1,false,true]]);
assert.deepEqual(dateOptions(rows,{...q,country:""})[0],{date:"2026-12-04",nights:[9],count:1,changeNights:false,changeDates:false});
assert.equal(dateOptions(rows,q,()=>false).length,0);
assert.equal(dateOptions(rows,{...q,origin:"Красноярск"}).length,0);
assert.equal(dateOptions([...rows,row("Иркутск","Китай","2026-02-30",9)],q).length,2);
assert.equal(dateOptions([...rows,row("Иркутск","Китай","2026-12-15",9)],q)[0].count,2);
assert.deepEqual(dateOptions(rows,{...q,nights:[]})[0].nights,[5]);
console.log("JAMAICA_EXACT_DATE_OPTIONS_PASS");

assert.deepEqual(otherCities(rows,q),[{origin:"Москва",count:1,countries:["Китай"]}]);
assert.equal(otherCities(rows,{...q,allowedOrigins:["Иркутск"]}).length,0);
assert.equal(otherCities(rows,{...q,nights:[7]}).length,0);
assert.equal(otherCities(rows,q,()=>false).length,0);
assert.equal(otherCities(rows,{...q,country:"Вьетнам"}).length,0);
assert.equal(otherCities(rows,{...q,from:"2026-12-05"}).length,0);
console.log("JAMAICA_EXPLICIT_OTHER_CITY_OPTIONS_PASS");

const pick=globalThis.JamaicaSearchRecovery.representative;
const candidates=[{...row("Москва","Вьетнам","2026-12-04",9),price:1},
 {...row("Иркутск","Вьетнам","2026-12-04",7),price:2},
 {...row("Иркутск","Вьетнам","2026-12-04",9),price:100},
 {...row("Иркутск","Вьетнам","2026-12-04",9),price:80},
 {...row("Иркутск","Вьетнам","2026-12-05",9),price:3}];
const option={country:"Вьетнам",date:"2026-12-04",nights:[9]};
assert.equal(pick(candidates,option,"иркутск",()=>true,(a,b)=>a.price-b.price),candidates[3]);
assert.equal(pick(candidates,option,"Иркутск",x=>x.price>=100),candidates[2]);
assert.equal(pick(candidates,option,"Иркутск",()=>false),null);
assert.equal(pick(candidates,{...option,country:"Египет"},"Иркутск"),null);
assert.equal(pick(candidates,option,"Красноярск"),null);
console.log("JAMAICA_ACTUAL_ALTERNATIVE_CARD_SELECTION_PASS");

// A selected country must not hide the ninth or later verified destination.
const broadCountries=["Вьетнам","Таиланд","Индия","Египет","Турция","Индонезия","Мальдивы","Сейшелы","Шри-Ланка","ОАЭ","Россия","Абхазия"];
const broad=broadCountries.map(country=>row("Иркутск",country,"2026-12-04",9));
const allAlternatives=otherCountryOptions(broad,q);
assert.equal(allAlternatives.length,broadCountries.length);
assert.deepEqual(new Set(allAlternatives.map(x=>x.country)),new Set(broadCountries));
assert.equal(otherCountryOptions([...broad,row("Москва","Япония","2026-12-04",9)],q).length,broadCountries.length);
console.log("JAMAICA_ALL_ELIGIBLE_ALTERNATIVE_COUNTRIES_PASS");

const flexibleCities=globalThis.JamaicaSearchRecovery.flexibleCities;
const flexibleRows=[row("Москва","Китай","2026-12-12",9),row("Москва","Китай","2026-12-12",9),row("Москва","Вьетнам","2026-12-05",5),row("Красноярск","Таиланд","2026-12-04",9),row("Иркутск","Китай","2026-12-15",9),row("Омск","Китай","2026-02-30",9)];
const fc=flexibleCities(flexibleRows,q);
assert.deepEqual(fc.map(x=>[x.origin,x.country,x.date,x.count,x.changeCountry,x.changeDates,x.changeNights]),[["Москва","Китай","2026-12-12",2,false,true,false],["Красноярск","Таиланд","2026-12-04",1,true,false,false]]);
assert.deepEqual(flexibleCities(flexibleRows,{...q,allowOtherCountries:false}).map(x=>x.origin),["Москва"]);
assert.deepEqual(flexibleCities(flexibleRows,{...q,allowedOrigins:["Красноярск"]}).map(x=>x.origin),["Красноярск"]);
assert.equal(flexibleCities(flexibleRows,q,()=>false).length,0);
assert.equal(flexibleCities([row("Москва","Китай","2026-12-04",9)],q).length,0);
assert.equal(flexibleCities([row("Москва","Китай","2026-12-04",5)],q)[0].changeNights,true);
console.log("JAMAICA_EXPLICIT_FLEXIBLE_OTHER_CITY_RECOVERY_PASS");


import "./traveler-party.js";
const savedSearch=globalThis.JamaicaSearchRecovery.savedSearch;
const context={origins:["Иркутск","Москва"],countries:["Китай","Вьетнам"],today:"2026-11-27",travelers:globalThis.JamaicaTravelers};
const input={origin:"Иркутск",country:"Китай",date:"2026-12-01",dateTo:"2027-01-15",nights:[10,7,10],rooms:[{adults:2,child_ages:[6]},{adults:1,child_ages:[]}],budget:60000,hotel:"Hotel",price:123,phone:"not retained"};
const out=savedSearch(input,context);
assert.deepEqual(out.nights,[7,10]);
assert.deepEqual(out.rooms,input.rooms);
assert.equal(out.budget,60000);
assert.equal(out.dateTo,"2027-01-15");
assert.equal("price" in out,false);
assert.equal("phone" in out,false);
assert.deepEqual(input.nights,[10,7,10]);
for(const patch of [{origin:"Unknown"},{country:"Unknown"},{date:"2026-11-26"},{dateTo:"2026-11-30"},{date:"2027-02-30"},{nights:[2]},{rooms:[{adults:1,child_ages:[18]}]},{budget:-1},{hotel:"<script>"}])assert.equal(savedSearch({...input,...patch},context),null);
assert.ok(savedSearch({...input,date:"",dateTo:"",country:"",budget:0,nights:[]},context));
console.log("JAMAICA_V103_LOCAL_SAVED_SEARCH_PASS");

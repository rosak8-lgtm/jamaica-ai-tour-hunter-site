import fs from "node:fs";
import vm from "node:vm";
import assert from "node:assert/strict";

const src=fs.readFileSync("scripts/country-offer-balance.js","utf8");
new vm.Script(src,{filename:"country-offer-balance.js"});
const context={window:{}};
vm.runInNewContext(src,context);
const {countryCounts,compareCountries,interleaveCountries}
  =context.window.JamaicaCountryOffers;
const make=(country,i,origin="Иркутск")=>({country,id:i,origin,
  depart_date:"2027-01-01",price_reference_rub:70000+i});
const countries=["Албания","Азербайджан","Болгария","Греция","Япония",
 "Филиппины","Камбоджа","Индонезия","Мальдивы","Куба","Египет",
 "Абхазия","Австрия","Бразилия","Индия","Италия","Мексика",
 "Оман","ОАЭ","Россия","Сейшелы","Турция","Узбекистан","Сингапур",
 "Испания","Шри-Ланка","Малайзия","Катар","Сербия","Тунис",
 "Таиланд","Китай","Вьетнам","Фиджи"];
const source=countries.flatMap((country,index)=>[
 make(country,index*10),make(country,index*10+1)]);
// Neither 200 very cheap Thai rows nor alphabetic country names may bury
// real Vietnam, China, or other destinations in the first 30 cards.
source.unshift(...Array.from({length:200},(_,i)=>make("Таиланд",1000+i)));
const before=source.map(x=>x.id);
const result=interleaveCountries(source);
assert.equal(result.length,source.length);
assert.deepEqual(Array.from(result.slice(0,3),x=>x.country),
 ["Таиланд","Китай","Вьетнам"]);
assert.equal(new Set(result.slice(0,30).map(x=>x.country)).size,30,
 "First 30 displayed tours must include 30 different source-backed countries");
assert.equal(new Set(result.slice(0,countries.length).map(x=>x.country)).size,
 countries.length,
 "All verified countries must appear before a country repeats");
assert.deepEqual(source.map(x=>x.id),before,"Never mutate supplier catalog");
assert.deepEqual(new Set(result.map(x=>x.id)),new Set(before),
 "Never lose or invent supplier rows");
assert.equal(result.filter(x=>x.country==="Таиланд").length,202);
const counts=countryCounts(source," иркутск ");
assert.equal(counts.get("Таиланд"),202);
assert.equal(counts.get("Китай"),2);
assert.equal(counts.size,countries.length);
const mixed=[...source,make("Китай",9999,"Москва")];
assert.equal(countryCounts(mixed,"Иркутск").get("Китай"),2,
 "Don't advertise another departure city in current filters");
assert.equal(countryCounts(mixed,"МОСКВА").size,1);
assert.equal(countryCounts(mixed,"Москва").get("Китай"),1);
assert.equal(countryCounts(mixed,"Нет такого города").size,0);
assert.equal(compareCountries("Таиланд","Китай")<0,true);
assert.equal(compareCountries("Китай","Вьетнам")<0,true);
assert.equal(compareCountries("Вьетнам","Абхазия")<0,true);
assert.equal(interleaveCountries([]).length,0);
assert.equal(countryCounts(null,"Иркутск").size,0);
console.log("JAMAICA_COUNTRY_BALANCED_RESULTS_ALL_COUNTRIES_PASS");

/* Search diagnostics over ALREADY eligible rows; never bypass proof policy. */
(function(root){
"use strict";
function analyze(rows,q,extra=()=>true){
 const norm=x=>String(x||"").trim().toLocaleLowerCase("ru");
 const city=rows.filter(x=>norm(x.origin)===norm(q.origin));
 const country=city.filter(x=>!q.country||norm(x.country)===norm(q.country));
 const dateOK=x=>(!q.from||x.depart_date>=q.from)&&(!q.to||x.depart_date<=q.to);
 const nightOK=x=>!q.nights.length||q.nights.includes(x.nights);
 const dates=country.filter(dateOK), nights=dates.filter(nightOK);
 const extraRows=country.filter(extra);
 const alternatives=[
  {key:"nights",count:extraRows.filter(dateOK).length,enabled:q.nights.length>0},
  {key:"dates",count:extraRows.filter(nightOK).length,enabled:!!(q.from||q.to)},
  {key:"both",count:extraRows.length,enabled:!!(q.from||q.to)&&q.nights.length>0},
  {key:"countries",count:city.filter(x=>norm(x.country)!==norm(q.country)&&dateOK(x)&&nightOK(x)&&extra(x)).length,enabled:!!q.country}
 ].filter(x=>x.enabled&&x.count>0);
 return {city:city.length,country:country.length,dates:dates.length,nights:nights.length,
  durations:[...new Set(dates.map(x=>x.nights))].sort((a,b)=>a-b),
  alternatives};
}
// Alternative exact departures, using only rows already passed through the
// strict visual gate. Preserve selected nights and all other active filters.
function departures(rows,q,extra=()=>true){
 const norm=x=>String(x||"").trim().toLocaleLowerCase("ru");
 const day=x=>/^\d{4}-\d{2}-\d{2}$/.test(x||"")?Date.parse(x+"T00:00:00Z"):NaN;
 const from=day(q.from),to=day(q.to),groups=new Map();
 for(const x of rows){
  if(norm(x.origin)!==norm(q.origin)||!x.country||!Number.isFinite(day(x.depart_date))||
    (q.nights.length&&!q.nights.includes(x.nights))||!extra(x))continue;
  const same=!q.country||norm(x.country)===norm(q.country);
  if(!same&&q.allowOtherCountries===false)continue;
  const inside=(!Number.isFinite(from)||day(x.depart_date)>=from)&&(!Number.isFinite(to)||day(x.depart_date)<=to);
  if(same&&inside)continue;
  const key=JSON.stringify([x.country,x.depart_date]);
  if(!groups.has(key))groups.set(key,{country:x.country,date:x.depart_date,count:0,nights:new Set(),same});
  const g=groups.get(key);g.count++;g.nights.add(x.nights);
 }
 const distance=g=>Math.max(0,Number.isFinite(from)?from-day(g.date):0,Number.isFinite(to)?day(g.date)-to:0);
 const compare=(a,b)=>distance(a)-distance(b)||a.date.localeCompare(b.date)||a.country.localeCompare(b.country,"ru");
 const values=[...groups.values()];
 return [...values.filter(g=>g.same).sort(compare).slice(0,3),
         ...values.filter(g=>!g.same).sort(compare).slice(0,3)]
  .map(g=>({...g,nights:[...g.nights].sort((a,b)=>a-b)}));
}
// Show a concrete, selectable date for every other verified country.
// Prefer current dates and nights, then explicitly label relaxed filters.
function otherCountryOptions(rows,q,extra=()=>true){
 const norm=x=>String(x||"").trim().toLocaleLowerCase("ru");
 if(!norm(q.origin)||!norm(q.country)||q.allowOtherCountries===false)return [];
 const day=s=>/^\d{4}-\d{2}-\d{2}$/.test(s||"")?Date.parse(s+"T00:00:00Z"):NaN;
 const from=day(q.from),to=day(q.to),selected=Array.isArray(q.nights)?q.nights:[];
 const groups=new Map();
 for(const x of rows){
  if(norm(x.origin)!==norm(q.origin)||!x.country||norm(x.country)===norm(q.country)||
     !Number.isFinite(day(x.depart_date))||!Number.isInteger(x.nights)||!extra(x))continue;
  const key=JSON.stringify([x.country,x.depart_date]);
  if(!groups.has(key))groups.set(key,{country:x.country,date:x.depart_date,counts:new Map()});
  const g=groups.get(key);g.counts.set(x.nights,(g.counts.get(x.nights)||0)+1);
 }
 const candidates=[];
 for(const g of groups.values()){
  const all=[...g.counts.keys()].sort((a,b)=>a-b),matched=all.filter(n=>!selected.length||selected.includes(n));
  const changeNights=matched.length===0;
  const nights=changeNights?all:matched;
  const d=day(g.date),distance=Math.max(0,Number.isFinite(from)?from-d:0,Number.isFinite(to)?d-to:0);
  candidates.push({country:g.country,date:g.date,nights,count:nights.reduce((n,v)=>n+g.counts.get(v),0),
   changeNights,changeDates:distance>0,distance});
 }
 const order=(a,b)=>Number(a.changeNights)+Number(a.changeDates)-Number(b.changeNights)-Number(b.changeDates)||
   Number(a.changeNights)-Number(b.changeNights)||a.distance-b.distance||b.count-a.count||a.date.localeCompare(b.date)||a.country.localeCompare(b.country,"ru");
 const unique=new Map();
 for(const g of candidates.sort(order))if(!unique.has(norm(g.country)))unique.set(norm(g.country),g);
 return [...unique.values()];
}
// Concrete date/night groups for the current city and country. Only
// already eligible rows are accepted by the caller. Never widen filters
// without an explicit customer click. Counts refer to the exact option.
function dateOptions(rows,q,extra=()=>true){
 const norm=x=>String(x||"").trim().toLocaleLowerCase("ru");
 if(!norm(q.origin))return [];
 const selected=Array.isArray(q.nights)?q.nights:[];
 const groups=new Map();
 for(const x of rows){
  if(norm(x.origin)!==norm(q.origin)||(q.country&&norm(x.country)!==norm(q.country))||
     !/^\d{4}-\d{2}-\d{2}$/.test(x.depart_date||"")||
     !Number.isInteger(x.nights)||x.nights<3||x.nights>180||!extra(x))continue;
  const day=Date.parse(x.depart_date+"T00:00:00Z");
  if(!Number.isFinite(day)||new Date(day).toISOString().slice(0,10)!==x.depart_date)continue;
  if(!groups.has(x.depart_date))groups.set(x.depart_date,new Map());
  const g=groups.get(x.depart_date);g.set(x.nights,(g.get(x.nights)||0)+1);
 }
 const results=[];
 for(const [date,g] of groups){
  const all=[...g.keys()].sort((a,b)=>a-b);
  const match=all.filter(n=>!selected.length||selected.includes(n));
  const nights=match.length?match:all;
  results.push({date,nights,count:nights.reduce((sum,n)=>sum+g.get(n),0),
    changeNights:!match.length,changeDates:!!((q.from&&date<q.from)||(q.to&&date>q.to))});
 }
 return results.sort((a,b)=>Number(a.changeDates)+Number(a.changeNights)-Number(b.changeDates)-Number(b.changeNights)||
  Number(a.changeNights)-Number(b.changeNights)||a.date.localeCompare(b.date));
}
// Alternatives from other cities must be a separate, explicit choice.
// Keep the requested country, date range, nights and extra filters.
// If they do not match, do not claim an alternative.
function otherCities(rows,q,extra=()=>true){
 const norm=x=>String(x||"").trim().toLocaleLowerCase("ru");
 if(!norm(q.origin))return [];
 const allowed=Array.isArray(q.allowedOrigins)?new Set(q.allowedOrigins):null;
 const cities=new Map();
 for(const x of rows){
  if(!x||typeof x.origin!=="string"||!norm(x.origin)||norm(x.origin)===norm(q.origin)||
     (allowed&&!allowed.has(x.origin))||
     (q.country&&norm(x.country)!==norm(q.country))||
     !/^\d{4}-\d{2}-\d{2}$/.test(x.depart_date||"")||
     (q.from&&x.depart_date<q.from)||(q.to&&x.depart_date>q.to)||
     (q.nights.length&&!q.nights.includes(x.nights))||!extra(x))continue;
  if(!cities.has(x.origin))cities.set(x.origin,{origin:x.origin,count:0,countries:new Set()});
  const g=cities.get(x.origin);g.count++;g.countries.add(x.country);
 }
 return [...cities.values()].sort((a,b)=>b.count-a.count||a.origin.localeCompare(b.origin,"ru"))
  .slice(0,8).map(g=>({...g,countries:[...g.countries].sort((a,b)=>a.localeCompare(b,"ru"))}));
}
// Explicit fallback when a different departure city alone cannot satisfy the
// request. Group actual eligible rows; never silently change user filters.
function flexibleCities(rows,q,extra=()=>true){
 const norm=x=>String(x||"").trim().toLocaleLowerCase("ru");
 const day=s=>{
   if(!/^\d{4}-\d{2}-\d{2}$/.test(s||""))return NaN;
   const t=Date.parse(s+"T00:00:00Z");
   return Number.isFinite(t)&&new Date(t).toISOString().slice(0,10)===s?t:NaN;
 };
 if(!norm(q.origin))return [];
 const allowed=Array.isArray(q.allowedOrigins)?new Set(q.allowedOrigins):null;
 const from=day(q.from),to=day(q.to),nights=Array.isArray(q.nights)?q.nights:[];
 const groups=new Map();
 for(const x of rows){
  if(!x||!norm(x.origin)||norm(x.origin)===norm(q.origin)||!norm(x.country)||
    (allowed&&!allowed.has(x.origin))||!Number.isFinite(day(x.depart_date))||
    !Number.isInteger(x.nights)||x.nights<3||x.nights>180||!extra(x))continue;
  const changeCountry=!!q.country&&norm(x.country)!==norm(q.country);
  if(changeCountry&&q.allowOtherCountries===false)continue;
  const changeNights=!!nights.length&&!nights.includes(x.nights);
  const d=day(x.depart_date),distance=Math.max(0,Number.isFinite(from)?from-d:0,Number.isFinite(to)?d-to:0);
  const changeDates=distance>0;
  if(!changeCountry&&!changeNights&&!changeDates)continue;
  const key=JSON.stringify([x.origin,x.country,x.depart_date,x.nights]);
  if(!groups.has(key))groups.set(key,{origin:x.origin,country:x.country,date:x.depart_date,nights:[x.nights],count:0,changeCountry,changeNights,changeDates,distance});
  groups.get(key).count++;
 }
 const rank=g=>Number(g.changeCountry)+Number(g.changeNights)+Number(g.changeDates);
 const ordered=[...groups.values()].sort((a,b)=>rank(a)-rank(b)||
   Number(a.changeCountry)-Number(b.changeCountry)||Number(a.changeNights)-Number(b.changeNights)||
   a.distance-b.distance||b.count-a.count||a.date.localeCompare(b.date)||
   a.origin.localeCompare(b.origin,"ru")||a.country.localeCompare(b.country,"ru")||a.nights[0]-b.nights[0]);
 const unique=new Map();
 for(const g of ordered)if(!unique.has(norm(g.origin)))unique.set(norm(g.origin),g);
 return [...unique.values()].slice(0,8);
}
// Select an actual row for a displayed option, never synthesize a tour.
function representative(rows,opt,origin,extra=()=>true,compare){
 if(!Array.isArray(rows)||!opt||!Array.isArray(opt.nights)||!origin)return null;
 const norm=x=>String(x||"").trim().toLocaleLowerCase("ru");
 const matches=rows.filter(x=>x&&norm(x.origin)===norm(origin)&&
   norm(x.country)===norm(opt.country)&&x.depart_date===opt.date&&
   opt.nights.includes(x.nights)&&extra(x));
 if(typeof compare==="function")matches.sort(compare);
 return matches[0]||null;
}
// Explicit, local-only saved search. No supplier calls, offers, contact or payment data.
function savedSearch(q,{origins,countries,today,travelers}){
 const clean=(s,max)=>typeof s==="string"&&s.length<=max&&s===s.trim()&&!/[<>\x00-\x1f\x7f]/.test(s);
 const validDay=s=>{
   if(!/^20\d{2}-\d{2}-\d{2}$/.test(s||""))return false;
   const d=Date.parse(s+"T00:00:00Z");
   return Number.isFinite(d)&&new Date(d).toISOString().slice(0,10)===s;
 };
 if(!q||!Array.isArray(origins)||!Array.isArray(countries)||!travelers||
    !validDay(today)||!origins.includes(q.origin)||
    !clean(q.country,100)||(q.country&&!countries.includes(q.country))||
    !clean(q.date,10)||!clean(q.dateTo,10)||
    (q.date&&(!validDay(q.date)||q.date<today))||
    (q.dateTo&&(!validDay(q.dateTo)||q.dateTo<today))||
    (q.date&&q.dateTo&&q.date>q.dateTo)||
    !Array.isArray(q.nights)||q.nights.length>178||
    q.nights.some(n=>!Number.isInteger(n)||n<3||n>180)||
    !clean(q.hotel,100)||!Number.isSafeInteger(q.budget)||
    (q.budget!==0&&(q.budget<1000||q.budget>10000000)))return null;
 const rooms=travelers.normalize(q.rooms);
 if(!rooms)return null;
 return {origin:q.origin,country:q.country,date:q.date,dateTo:q.dateTo,
    nights:[...new Set(q.nights)].sort((a,b)=>a-b),rooms,budget:q.budget,hotel:q.hotel};
}
// Historical date options are NEVER offer rows. Their observation clock is immutable.
function hourlyDateGroups(payload,now=Date.now()){
 if(!payload||payload.schema!=="jamaica.recent-checked-dates.v1"||
    payload.classification!=="HISTORICAL_SEARCH_ONLY_NOT_OFFERS"||
    !Array.isArray(payload.groups)||payload.groups.length>2000||!Number.isFinite(now))return [];
 const today=new Date(now).toISOString().slice(0,10),end=new Date(now+730*86400000).toISOString().slice(0,10);
 const groups=new Map(),keys=["origin","country","date","nights","observed_at_utc","count","last_min_rub"];
 for(const g of payload.groups){
  if(!g||typeof g!=="object"||Object.keys(g).length!==keys.length||!keys.every(k=>Object.hasOwn(g,k)))continue;
  if(![g.origin,g.country].every(s=>typeof s==="string"&&s.length>=2&&s.length<=100&&s===s.trim()&&!/[<>\x00-\x1f]/.test(s)))continue;
  if(typeof g.date!=="string"||!/^20\d{2}-\d{2}-\d{2}$/.test(g.date)||g.date<today||g.date>end)continue;
  const day=Date.parse(g.date+"T00:00:00Z");
  if(!Number.isFinite(day)||new Date(day).toISOString().slice(0,10)!==g.date)continue;
  if(typeof g.observed_at_utc!=="string"||!/(Z|[+-]\d{2}:\d{2})$/.test(g.observed_at_utc))continue;
  const stamp=Date.parse(g.observed_at_utc),age=now-stamp;
  if(!Number.isFinite(stamp)||age< -30000||age>(day-Date.parse(today+'T00:00:00Z')<=7*86400000?1800000:7200000)||!Number.isInteger(g.nights)||g.nights<3||g.nights>180||
     !Number.isInteger(g.count)||g.count<1||g.count>10000||!Number.isSafeInteger(g.last_min_rub)||g.last_min_rub<1000||g.last_min_rub>10000000)continue;
  const key=JSON.stringify([g.origin,g.country,g.date,g.nights]),prior=groups.get(key);
  if(!prior||Date.parse(prior.observed_at_utc)<stamp)groups.set(key,{...g});
 }
 return [...groups.values()];
}
root.JamaicaSearchRecovery=Object.freeze({analyze,departures,otherCountryOptions,dateOptions,otherCities,flexibleCities,representative,savedSearch,hourlyDateGroups});
})(globalThis);

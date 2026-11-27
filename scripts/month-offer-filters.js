/* JAMAICA: real published departure-month shortcuts.
   No invented departures, supplier stock or prices. */
(function(root){
"use strict";
const MONTH=/^(20\d{2})-(0[1-9]|1[0-2])$/;
function range(month){
 if(typeof month!=="string")return null;
 const m=MONTH.exec(month);
 if(!m)return null;
 const year=Number(m[1]),number=Number(m[2]);
 return {
  from:month+"-01",
  to:new Date(Date.UTC(year,number,0)).toISOString().slice(0,10)
 };
}
function activeMonth(from,to){
 if(typeof from!=="string"||typeof to!=="string"||
    from.length<7||from.slice(0,7)!==to.slice(0,7))return null;
 const month=from.slice(0,7),period=range(month);
 return period&&period.from===from&&period.to===to?month:null;
}
function monthsFor(rows,{origin="",country="",today=""}={}){
 const from=String(origin).trim().toLocaleLowerCase("ru");
 const destination=String(country).trim().toLocaleLowerCase("ru");
 const counts=new Map();
 if(!Array.isArray(rows))return counts;
 for(const row of rows){
  if(!row||typeof row.depart_date!=="string"||
     !/^20\d{2}-(0[1-9]|1[0-2])-[0-3]\d$/.test(row.depart_date)||
     !range(row.depart_date.slice(0,7))||
     row.depart_date>range(row.depart_date.slice(0,7)).to||
     typeof row.origin!=="string"||typeof row.country!=="string"||
     (from&&row.origin.trim().toLocaleLowerCase("ru")!==from)||
     (destination&&row.country.trim().toLocaleLowerCase("ru")!==destination)||
     (today&&row.depart_date<today))continue;
  const key=row.depart_date.slice(0,7);
  counts.set(key,(counts.get(key)||0)+1);
 }
 return new Map([...counts].sort((a,b)=>a[0].localeCompare(b[0])));
}
// Discovery metadata is not inventory. Never use another city's coverage.
function observedMonthsFor(coverage,{origin="",country="",today=""}={}){
 const norm=x=>String(x||"").trim().toLocaleLowerCase("ru");
 if(norm(origin)!=="иркутск"||!Array.isArray(coverage))return [];
 const result=new Set();
 for(const item of coverage){
  if(!item||typeof item.country!=="string"||
     (norm(country)&&norm(item.country)!==norm(country))||
     !Array.isArray(item.sampled_departure_months))continue;
  for(const month of item.sampled_departure_months){
   const period=range(month);
   if(period&&(!today||period.to>=today))result.add(month);
  }
 }
 return [...result].sort().slice(0,24);
}
root.JamaicaMonths=Object.freeze({range,activeMonth,monthsFor,observedMonthsFor});
})(typeof window!=="undefined"?window:globalThis);

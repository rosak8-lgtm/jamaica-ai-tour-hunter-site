/* Non-commercial read-only source scanning coverage, NEVER an offer.
 * Supports old source-feed country stats and strict-public feed metadata.
 * Does not create preview IDs, prices, flight statuses or tour cards. */
(function(root){
"use strict";
const maxCountries=120,maxMonths=24;
function parse(feed){
 if(!feed||typeof feed!=="object"||feed.schema!=="jamaica.tour-previews.v1")
  return [];
 const list=feed.search_coverage&&Array.isArray(feed.search_coverage.countries)
   ?feed.search_coverage.countries:feed.countries_status;
 if(!Array.isArray(list)||list.length>maxCountries)return [];
 const unique=new Map();
 for(const item of list){
  if(!item||typeof item!=="object"||
     typeof item.country!=="string"||
     item.country.length<2||item.country.length>80||/[<>{}\x00-\x1f]/.test(item.country))
   continue;
  const count=item.source_rows_observed??item.previews;
  if(!Number.isSafeInteger(count)||count<=0||count>60000)continue;
  const months=(Array.isArray(item.sampled_departure_months)?
     item.sampled_departure_months:[]).filter(x=>
        typeof x==="string"&&/^20\d{2}-(0[1-9]|1[0-2])$/.test(x))
      .slice(0,maxMonths);
  if(unique.has(item.country))return [];
  unique.set(item.country,{
   country:item.country,source_rows_observed:count,
   sampled_departure_months:[...new Set(months)].sort()
  });
 }
 const priority=new Map([["Таиланд",0],["Китай",1],["Вьетнам",2]]);
 return [...unique.values()].sort((a,b)=>
  (priority.get(a.country)??99)-(priority.get(b.country)??99)||
  a.country.localeCompare(b.country,"ru"));
}
root.JamaicaSourceCoverage=Object.freeze({parse});
})(typeof window!=="undefined"?window:globalThis);

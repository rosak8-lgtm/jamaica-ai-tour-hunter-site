/* JAMAICA: source-backed multi-country discovery and balanced search.
   Pure data grouping. No network, prices, booking or fabricated offers. */
(function(root){
"use strict";
const PRIORITY=Object.freeze(["Таиланд","Китай","Вьетнам"]);
const priorityIndex=new Map(PRIORITY.map((country,i)=>[country,i]));
function compareCountries(a,b){
 return (priorityIndex.get(a)??999)-(priorityIndex.get(b)??999)||
   a.localeCompare(b,"ru");
}
function countryCounts(rows,origin){
 const wanted=typeof origin==="string"?origin.trim().toLocaleLowerCase("ru"):"";
 const counts=new Map();
 if(!Array.isArray(rows))return counts;
 for(const row of rows){
  if(!row||typeof row.country!=="string"||!row.country||
     typeof row.origin!=="string")continue;
  if(wanted&&row.origin.trim().toLocaleLowerCase("ru")!==wanted)continue;
  counts.set(row.country,(counts.get(row.country)||0)+1);
 }
 return counts;
}
function interleaveCountries(rows){
 if(!Array.isArray(rows)||rows.length===0)return [];
 const groups=new Map();
 for(const item of rows){
  if(!item||typeof item.country!=="string"||!item.country)continue;
  if(!groups.has(item.country))groups.set(item.country,[]);
  groups.get(item.country).push(item);
 }
 const keys=[...groups.keys()].sort(compareCountries);
 const output=[],positions=new Map(keys.map(k=>[k,0]));
 let added=true;
 while(added){
  added=false;
  for(const key of keys){
   const pos=positions.get(key),group=groups.get(key);
   if(pos<group.length){
    output.push(group[pos]);
    positions.set(key,pos+1);
    added=true;
   }
  }
 }
 return output;
}
root.JamaicaCountryOffers=Object.freeze({PRIORITY,compareCountries,
 countryCounts,interleaveCountries});
})(typeof window!=="undefined"?window:globalThis);

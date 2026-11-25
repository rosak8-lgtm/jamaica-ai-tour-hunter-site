/* Independent second-operator reference feed. Never authorizes checkout. */
(function(root){
"use strict";
const SCHEMA="jamaica.pegas-reference-catalog.v1";
const STATUS="PEGAS_APPLICATION_PRICE_REFERENCE_ONLY";
const SOURCE="PEGAS_OPEN_APPLICATION_MANDATORY_FEES_INCLUDED";
const FLAGS=["hotel_filter_verified","flight_filter_verified","cheapest_eligible_price_clicked","final_price_observed","mandatory_fees_included"];
function label(s){return typeof s==="string"&&s.length>0&&s.length<=200&&s===s.trim()&&!/[<>{}\x00-\x1f]/.test(s);}
function validDate(s){
 if(typeof s!=="string"||!/^\d{4}-\d{2}-\d{2}$/.test(s))return false;
 const t=Date.parse(s+"T00:00:00Z");
 return Number.isFinite(t)&&new Date(t).toISOString().slice(0,10)===s;
}
function fresh(s,now){
 if(typeof s!=="string"||!/(?:Z|[+-]\d{2}:\d{2})$/.test(s))return false;
 const t=Date.parse(s);return Number.isFinite(t)&&now-t>=-30000&&now-t<=900000;
}
function eligible(r,now=Date.now()){
 if(!r||typeof r!=="object"||!Number.isFinite(now)||!/^pg_[a-f0-9]{24}$/.test(r.id||"")||
 r.status!==STATUS||r.price_source!==SOURCE||r.price_reference_party!=="TWO_ADULTS"||
 !["origin","country","hotel","room","resort"].every(k=>label(r[k]))||
 !["bookable","quote_verified","availability_verified","flight_verified"].every(k=>r[k]===false)||
 !validDate(r.depart_date)||r.depart_date<new Date(now).toISOString().slice(0,10)||
 !Number.isInteger(r.nights)||r.nights<3||r.nights>180||
 (r.country==="Вьетнам"&&[45,60].includes(r.nights))||
 !Number.isSafeInteger(r.price_reference_rub)||r.price_reference_rub<=0||r.price_reference_rub>10000000)return false;
 const e=r.evidence;
 return !!e&&FLAGS.every(k=>e[k]===true)&&e.observed_at_utc===r.price_observed_at_utc&&fresh(e.observed_at_utc,now);
}
function parse(feed,now=Date.now()){
 if(!feed||feed.schema!==SCHEMA||feed.bookable!==false||feed.quote_verified!==false||
 !Array.isArray(feed.previews)||feed.previews.length>5000||!fresh(feed.refreshed_at_utc,now))return [];
 const counts=new Map();
 for(const r of feed.previews)if(r&&typeof r.id==="string")counts.set(r.id,(counts.get(r.id)||0)+1);
 return feed.previews.filter(r=>eligible(r,now)&&counts.get(r.id)===1);
}
async function load(){
 try{
  const res=await fetch("./application-reference.json",{cache:"no-store",signal:AbortSignal.timeout(5000)});
  if(!res.ok)return [];
  return parse(await res.json());
 }catch{return [];}
}
root.JamaicaApplicationReference=Object.freeze({eligible,parse,load});
})(globalThis);

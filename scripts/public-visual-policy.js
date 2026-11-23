/* JAMAICA customer publication gate.
 * A price-list item is NOT a tour card. Display only an exact
 * same-preview route-first BG badge + two green flight-icon observation.
 * Missing, stale, invalid or cross-ID evidence always means HIDE.
 * Evidence is not a real quote, a seat hold or permission to charge.
 */
(function(root){
"use strict";
function eligible(row,proofs,now=Date.now()){
 if(!row||typeof row!=="object"||!proofs||typeof proofs.get!=="function"||
    !Number.isFinite(now)||row.status!=="REFERENCE_PRICE_LIST_ONLY"||
    row.bookable!==false||row.quote_verified!==false||
    row.availability_verified!==false||row.flight_verified!==false||
    !/^p_[0-9a-f]{24}$/.test(row.id||"")||
    typeof row.depart_date!=="string"||
    !/^\d{4}-\d{2}-\d{2}$/.test(row.depart_date)||
    row.depart_date<new Date(now).toISOString().slice(0,10))return false;
 const p=proofs.get(row.id);
 if(!p||p.preview_id!==row.id||
    p.route_best_price_seen!==true||p.both_green_planes_seen!==true||
    p.bookable!==false||p.quote_verified!==false||
    typeof p.observed_at_utc!=="string")return false;
 const checked=Date.parse(p.observed_at_utc);
 const age=now-checked;
 return Number.isFinite(checked)&&age>=-30000&&age<=15*60*1000;
}
function filter(rows,proofs,now=Date.now()){
 if(!Array.isArray(rows))return [];
 return rows.filter(x=>eligible(x,proofs,now));
}
async function load(){
 try{
  const response=await fetch("./tour-visual-evidence.json",{cache:"no-store"});
  if(!response.ok)throw Error("PROOF_FEED_NOT_AVAILABLE");
  const parsed=await response.json();
  if(!root.JamaicaVisualSelection)throw Error("NO_PROOF_VERIFIER");
  return root.JamaicaVisualSelection.read(parsed);
 }catch(error){
  return new Map();
 }
}
root.JamaicaPublicVisualPolicy=Object.freeze({eligible,filter,load});
})(typeof window!=="undefined"?window:globalThis);

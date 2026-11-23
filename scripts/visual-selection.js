/* Public display ONLY of time-bounded bot visual observations.
   Never a supplier hold, quote, payment permission or booking flag.
   The private contract verifier generates this document on Oracle. */
(function(root){
"use strict";
const MAX=300,TTL=15*60*1000;
function read(feed,now=Date.now()){
 if(!feed||typeof feed!=="object"||
    Object.keys(feed).sort().join("|")!==
      "availability_verified|bookable|entries|quote_verified|schema"||
    feed.schema!=="jamaica.visual-selection.v1"||
    feed.bookable!==false||feed.quote_verified!==false||
    feed.availability_verified!==false||!Array.isArray(feed.entries)||
    feed.entries.length>MAX||!Number.isFinite(now))return new Map();
 const map=new Map();
 for(const e of feed.entries){
  if(!e||typeof e!=="object"||
     Object.keys(e).sort().join("|")!==
      "both_green_planes_seen|observed_at_utc|preview_id|route_best_price_seen"||
     !/^p_[a-f0-9]{24}$/.test(e.preview_id||"")||
     e.route_best_price_seen!==true||e.both_green_planes_seen!==true||
     typeof e.observed_at_utc!=="string"){
    return new Map();
  }
  const time=Date.parse(e.observed_at_utc);
  if(!Number.isFinite(time)||map.has(e.preview_id))return new Map();
  // Stale records are removed, not interpreted as missing market inventory.
  if(now-time>=-30000&&now-time<=TTL)map.set(e.preview_id,{
   preview_id:e.preview_id,observed_at_utc:e.observed_at_utc,
   route_best_price_seen:true,both_green_planes_seen:true,
   bookable:false,quote_verified:false
  });
 }
 return map;
}
root.JamaicaVisualSelection=Object.freeze({read,TTL,MAX});
})(typeof window!=="undefined"?window:globalThis);

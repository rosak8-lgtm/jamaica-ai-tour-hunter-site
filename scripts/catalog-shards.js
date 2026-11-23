/* JAMAICA catalog shards: public, read-only, and strictly preliminary.
   Root tour-previews.json is limited to 8,000 for fast initial paint.
   Remaining source records live in same-origin bounded JSON shards. */
(function(){
"use strict";
const MAX_ROOT=8000,MAX_TOTAL=60000,MAX_SHARDS=13,MAX_SHARD_ROWS=4000;
// Six bounded parallel requests reveal more source countries sooner without a 13-file burst.
const SHARD_WINDOW=6;
function validRow(x){
 return x&&typeof x==="object"&&/^p_[a-f0-9]{24}$/.test(x.id||"")&&
    /^\d{7,20}$/.test(x.hotel_id||"")&&
    typeof x.country==="string"&&x.country.length>0&&
    typeof x.hotel==="string"&&x.hotel.length>0&&
    typeof x.room==="string"&&typeof x.origin==="string"&&
    typeof x.resort==="string"&&/^\d{4}-\d{2}-\d{2}$/.test(x.depart_date||"")&&
    Number.isInteger(x.nights)&&x.nights>=3&&x.nights<=180&&
    x.bookable===false&&x.quote_verified===false&&
    x.availability_verified===false&&x.flight_verified===false&&
    ["REFERENCE_PRICE_LIST_ONLY","PREVIOUSLY_SEEN_NOT_RECHECKED"].includes(x.status)&&
    (x.status!=="PREVIOUSLY_SEEN_NOT_RECHECKED"||
      (x.price_reference_rub==null&&x.price_reference_party==="UNVERIFIED"))&&
    (x.price_reference_rub==null||
      (Number.isSafeInteger(x.price_reference_rub)&&x.price_reference_rub>0&&
       x.price_reference_party==="TWO_ADULTS"));
}
function manifest(feed){
 if(!feed||feed.schema!=="jamaica.tour-previews.v1"||
    feed.bookable!==false||feed.quote_verified!==false||
    feed.availability_verified!==false||
    !Array.isArray(feed.previews)||feed.previews.length>MAX_ROOT||
    !feed.previews.every(validRow))throw Error("UNSAFE_PREVIEW_ROOT");
 const items=feed.shards;
 if(items===undefined)return [];
 if(!Array.isArray(items)||items.length>MAX_SHARDS)throw Error("UNSAFE_SHARD_MANIFEST");
 const seen=new Set();
 let total=feed.previews.length;
 for(const [i,p] of items.entries()){
  const expected="tour-previews-shards/part-"+String(i+1).padStart(3,"0")+".json";
  if(!p||p.path!==expected||seen.has(p.path)||
     !Number.isInteger(p.count)||p.count<1||p.count>MAX_SHARD_ROWS||
     !/^[a-f0-9]{64}$/.test(p.sha256||""))throw Error("UNSAFE_SHARD_ENTRY");
  seen.add(p.path);
  total+=p.count;
 }
 if(total>MAX_TOTAL||!Number.isInteger(feed.total_published_previews)||
    feed.total_published_previews!==total)throw Error("UNSAFE_PUBLISHED_COUNT");
 return items;
}
async function fetchShard(part,refreshed){
 const r=await fetch("./"+part.path,{cache:"no-store"});
 if(!r.ok)throw Error("CATALOG_SHARD_UNAVAILABLE");
 const payload=await r.json();
 if(payload.schema!=="jamaica.tour-preview-shard.v1"||
    payload.refreshed_at_utc!==refreshed||
    payload.bookable!==false||payload.quote_verified!==false||
    payload.availability_verified!==false||
    !Array.isArray(payload.previews)||payload.previews.length!==part.count||
    !payload.previews.every(validRow))throw Error("CATALOG_SHARD_MISMATCH");
 return payload.previews;
}
async function allPreviews(feed,onBatch){
 const parts=manifest(feed),rows=[...feed.previews],seen=new Set(rows.map(x=>x.id));
 if(seen.size!==rows.length)throw Error("DUPLICATE_PREVIEW_ROOT");
 // Show actual root results immediately, without waiting for all shards.
 if(onBatch)onBatch(rows,0,parts.length);
 for(let pos=0;pos<parts.length;pos+=SHARD_WINDOW){
  const fetched=await Promise.all(parts.slice(pos,pos+SHARD_WINDOW)
    .map(part=>fetchShard(part,feed.refreshed_at_utc)));
  for(const page of fetched){
   for(const x of page){
    if(seen.has(x.id))throw Error("DUPLICATE_SHARDED_PREVIEW");
    seen.add(x.id);rows.push(x);
   }
  }
  if(onBatch)onBatch(rows,Math.min(pos+SHARD_WINDOW,parts.length),parts.length);
 }
 if(parts.length&&rows.length!==feed.total_published_previews)
   throw Error("SHARDED_COUNT_MISMATCH");
 return rows;
}
async function findPreview(feed,id){
 const parts=manifest(feed);
 const first=feed.previews.find(x=>x.id===id);
 if(first)return first;
 for(let pos=0;pos<parts.length;pos+=SHARD_WINDOW){
  const fetched=await Promise.all(parts.slice(pos,pos+SHARD_WINDOW)
    .map(part=>fetchShard(part,feed.refreshed_at_utc)));
  for(const rows of fetched){
   const found=rows.find(x=>x.id===id);
   if(found)return found;
  }
 }
 return null;
}
window.JamaicaCatalog=Object.freeze({manifest,allPreviews,findPreview,validRow});
})();

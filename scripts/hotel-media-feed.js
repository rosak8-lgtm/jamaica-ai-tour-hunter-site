/* JAMAICA official licensed property photos: ID-indexed read-only shards.
   This is NOT a guess by hotel name, photo search or image scraping. */
(function(){
"use strict";
const INDEX_URL="./hotel-media-feed/index.json";
const indexPromise=fetch(INDEX_URL,{cache:"force-cache"})
  .then(r=>r.ok?r.json():null)
  .then(v=>v&&v.schema==="jamaica.hotel-media-feed-index.v1"&&
    v.entries&&typeof v.entries==="object"&&
    Number.isInteger(v.total_hotels)&&v.total_hotels>=0&&v.total_hotels<=50000?
    v:null).catch(()=>null);
const shardCache=new Map();
async function getApprovedEntry(id,country,name){
 if(typeof id!=="string"||!/^\d{7,20}$/.test(id)||
    typeof country!=="string"||typeof name!=="string")return null;
 const index=await indexPromise;
 if(!index)return null;
 const path=index.entries[id];
 if(typeof path!=="string"||
   !/^hotel-media-feed\/part-\d{4}\.json$/.test(path))return null;
 let pending=shardCache.get(path);
 if(!pending){
  pending=fetch("./"+path,{cache:"force-cache"})
    .then(r=>r.ok?r.json():null)
    .then(v=>v&&v.schema==="jamaica.hotel-media-feed-part.v1"&&
      v.hotels&&typeof v.hotels==="object"?v.hotels:null)
    .catch(()=>null);
  shardCache.set(path,pending);
 }
 const entry=(await pending)?.[id];
 if(!entry||entry.hotel_name!==name||entry.country!==country||
    entry.rights_verified!==true||
    entry.commercial_publication_allowed!==true||
    typeof entry.permission_reference!=="string"||
    entry.permission_reference.trim().length<12||
    typeof entry.rights_verified_at!=="string"||
    !/^\d{4}-\d{2}-\d{2}$/.test(entry.rights_verified_at)||
    typeof entry.rights_expires_at!=="string"||
    !/^\d{4}-\d{2}-\d{2}$/.test(entry.rights_expires_at)||
    !Number.isFinite(Date.parse(entry.rights_expires_at+"T23:59:59Z"))||
    Date.now()>Date.parse(entry.rights_expires_at+"T23:59:59Z")||
    !Array.isArray(entry.photos)||
    !Array.isArray(entry.approved_image_hosts)||
    !Array.isArray(entry.approved_source_hosts))return null;
 return entry;
}
window.JamaicaHotelMedia=Object.freeze({getApprovedEntry});
})();

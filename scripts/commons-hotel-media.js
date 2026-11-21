/* Only independently reviewed Wikidata property IDs and Commons file licenses.
   Photos load directly from Commons; never guess a hotel based on filename. */
(function(){
"use strict";
const allowable=new Set(["CC BY 2.0","CC BY 3.0","CC BY 4.0",
 "CC BY-SA 2.0","CC BY-SA 3.0","CC BY-SA 4.0",
 "CC0 1.0","Public domain"]);
const indexPromise=fetch("./hotel-open-media/index.json",{cache:"force-cache"})
 .then(r=>r.ok?r.json():null)
 .then(x=>x&&x.schema==="jamaica.hotel-open-media-index.v1"&&
    Number.isSafeInteger(x.total_hotels)&&x.total_hotels>=0&&x.total_hotels<=15000&&
    x.entries&&typeof x.entries==="object"?x:null)
 .catch(()=>null);
const cache=new Map();
function photoOK(p){
 if(!p||typeof p!=="object"||
    typeof p.file!=="string"||p.file.length<5||p.file.length>180||
    !/^[^/\\\x00-\x1f<>?%#]{5,180}\.(?:jpe?g|png|webp)$/i.test(p.file)||
    p.file.includes("..")||!allowable.has(p.license)||
    typeof p.author!=="string"||p.author.trim().length<3||
    typeof p.alt!=="string"||p.alt.length<10||
    !["hotel_property","hotel_exterior","hotel_public_area"].includes(p.kind)||
    typeof p.wikidata_qid!=="string"||!/^Q[1-9]\d{0,14}$/.test(p.wikidata_qid))
     return false;
 const src="https://commons.wikimedia.org/wiki/Special:FilePath/"+
     encodeURIComponent(p.file)+"?width=720";
 const source="https://commons.wikimedia.org/wiki/File:"+
     encodeURIComponent(p.file.replaceAll(" ","_"))
      .replaceAll("%28","(").replaceAll("%29",")");
 if(p.src!==src||p.source!==source)return false;
 const lic=typeof p.license_url==="string"?p.license_url:"";
 if(p.license==="Public domain"){
   if(lic!=="https://commons.wikimedia.org/wiki/Commons:Licensing")return false;
 }else{
   const expected=p.license.startsWith("CC0")?
       "https://creativecommons.org/publicdomain/zero/1.0/":
       "https://creativecommons.org/licenses/"+
         (p.license.startsWith("CC BY-SA")?"by-sa/":"by/")+
         p.license.split(" ").at(-1)+"/";
   if(lic!==expected)return false;
 }
 return true;
}
async function get(id,country,name){
 if(typeof id!=="string"||!/^\d{7,20}$/.test(id)||
    typeof name!=="string"||typeof country!=="string")return null;
 const index=await indexPromise;
 if(!index)return null;
 const path=index.entries[id];
 if(typeof path!=="string"||
    !/^hotel-open-media\/part-\d{4}\.json$/.test(path))return null;
 let pending=cache.get(path);
 if(!pending){
   pending=fetch("./"+path,{cache:"force-cache"})
    .then(r=>r.ok?r.json():null)
    .then(d=>d&&d.schema==="jamaica.hotel-open-media-part.v1"&&
       d.hotels&&typeof d.hotels==="object"?d.hotels:null)
    .catch(()=>null);
   cache.set(path,pending);
 }
 const row=(await pending)?.[id];
 if(!row||row.hotel_name!==name||row.country!==country||
    row.identity_reviewed!==true||
    typeof row.wikidata_qid!=="string"||!/^Q[1-9]\d{0,14}$/.test(row.wikidata_qid)||
    typeof row.identity_review_reference!=="string"||
    !row.identity_review_reference.startsWith("https://")||
    !Array.isArray(row.photos))return null;
 const photos=row.photos.filter(p=>photoOK(p)&&p.wikidata_qid===row.wikidata_qid).slice(0,12);
 return photos.length?photos:null;
}
window.JamaicaOpenHotelMedia=Object.freeze({get,photoOK});
})();

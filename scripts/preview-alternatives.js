/* JAMAICA: real-price-list alternatives for one selected tour.
   Pure selection, no provider API or booking side effects, no imagined prices.
   Searches the FULL verified-shard catalog in the calling page. */
(function(root){
"use strict";
const MAX_CHOICES=12;
const TAGS=Object.freeze({
 sameHotel:"Тот же отель · другие варианты",
 sameResort:"Этот курорт · другой отель",
 sameCountry:"Эта страна · другие курорты",
 otherCountry:"Другие страны"
});
function choose(rows,selected,opts){
 const today=opts&&typeof opts.today==="string"?opts.today:
   new Date().toISOString().slice(0,10);
 if(!Array.isArray(rows)||!selected||typeof selected.id!=="string"||
    !/^\d{4}-\d{2}-\d{2}$/.test(today))return [];
 const eligible=[];
 const ids=new Set([selected.id]);
 for(const p of rows){
   if(!p||typeof p!=="object"||typeof p.id!=="string"||
      !/^p_[a-f0-9]{24}$/.test(p.id)||ids.has(p.id)||
      p.origin!==selected.origin||typeof p.country!=="string"||
      !p.country||typeof p.hotel_id!=="string"||
      !/^\d{7,20}$/.test(p.hotel_id)||
      typeof p.depart_date!=="string"||p.depart_date<=today||
      !/^\d{4}-\d{2}-\d{2}$/.test(p.depart_date)||
      !Number.isInteger(p.nights)||p.nights<3||p.nights>180||
      p.bookable!==false||p.quote_verified!==false||
      p.availability_verified!==false||p.flight_verified!==false||
      !["REFERENCE_PRICE_LIST_ONLY","PREVIOUSLY_SEEN_NOT_RECHECKED"].includes(p.status)||
      (p.status==="PREVIOUSLY_SEEN_NOT_RECHECKED"&&
       (p.price_reference_rub!=null||p.price_reference_party!=="UNVERIFIED"))){
      continue;
   }
   ids.add(p.id);
   const kind=p.hotel_id===selected.hotel_id?
     "sameHotel":p.country===selected.country&&p.resort===selected.resort?
     "sameResort":p.country===selected.country?"sameCountry":"otherCountry";
   eligible.push({row:p,kind});
 }
 // Proximity considers the actual requested departure and duration,
 // rather than sorting a 52k-row catalog by unrelated cheap fares.
 const departure=Date.parse(selected.depart_date+"T00:00:00Z");
 const score=r=>{
   const gap=Math.abs(Date.parse(r.depart_date+"T00:00:00Z")-departure)/86400000;
   return [Number.isFinite(gap)?gap:9999,
           Math.abs(r.nights-selected.nights),
           r.depart_date,r.country,r.hotel,r.id];
 };
 const cmp=(a,b)=>{
   const x=score(a.row),y=score(b.row);
   for(let i=0;i<x.length;i++){
     if(x[i]<y[i])return -1;
     if(x[i]>y[i])return 1;
   }
   return 0;
 };
 const result=[],used=new Set();
 function add(item){
   if(result.length<MAX_CHOICES&&!used.has(item.row.id)){
     result.push({row:item.row,kind:item.kind,label:TAGS[item.kind]});
     used.add(item.row.id);
   }
 }
 // Keep three slots for distinct other countries even if this hotel has
 // thousands of cheaper/repeated rows in the published preliminary feed.
 const per={sameHotel:[],sameResort:[],sameCountry:[],otherCountry:[]};
 for(const e of eligible)per[e.kind].push(e);
 for(const a of Object.values(per))a.sort(cmp);
 for(const kind of ["sameHotel","sameResort","sameCountry"]){
   const limit={sameHotel:4,sameResort:3,sameCountry:2}[kind];
   per[kind].slice(0,limit).forEach(add);
 }
 const destinations=new Map();
 for(const e of per.otherCountry){
   if(!destinations.has(e.row.country))destinations.set(e.row.country,[]);
   destinations.get(e.row.country).push(e);
 }
 // One option from each distinct country before any repeat country.
 const countryHeads=[...destinations.values()].map(x=>x[0]).sort(cmp);
 countryHeads.slice(0,3).forEach(add);
 // Remaining space goes to the best additional distinct-country result,
 // and finally to more relevant alternatives from the chosen hotel/region.
 for(const e of countryHeads.slice(3))add(e);
 for(const kind of ["sameHotel","sameResort","sameCountry","otherCountry"]){
   for(const e of per[kind]){if(result.length===MAX_CHOICES)break;add(e)}
 }
 return result;
}
root.JamaicaPreviewAlternatives=Object.freeze({choose,MAX_CHOICES,TAGS});
})(typeof window!=="undefined"?window:globalThis);

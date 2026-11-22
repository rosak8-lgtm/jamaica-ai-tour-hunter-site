/* JAMAICA: verified traveler composition, no fabricated tourist pricing.
   Rooms are booking groups, and child ages refer to tour departure date.
   The supplier must separately validate ages, room occupancy and live prices. */
(function(root){
 "use strict";
 const MAX_ROOMS=5,MAX_ADULTS=12,MAX_CHILDREN=10,MAX_CHILD_AGE=17;
 function validInt(x,min,max){return Number.isInteger(x)&&x>=min&&x<=max;}
 function normalize(rooms){
  if(!Array.isArray(rooms)||rooms.length<1||rooms.length>MAX_ROOMS)return null;
  let totalAdults=0,totalChildren=0;
  const clean=[];
  for(const r of rooms){
   if(!r||!validInt(r.adults,1,MAX_ADULTS)||!Array.isArray(r.child_ages)||
      r.child_ages.length>MAX_CHILDREN||
      r.child_ages.some(a=>!validInt(a,0,MAX_CHILD_AGE)))return null;
   totalAdults+=r.adults;totalChildren+=r.child_ages.length;
   clean.push({adults:r.adults,child_ages:[...r.child_ages]});
  }
  return totalAdults<=MAX_ADULTS&&totalChildren<=MAX_CHILDREN?clean:null;
 }
 function totals(rooms){
  const r=normalize(rooms);
  if(!r)return null;
  return {adults:r.reduce((n,x)=>n+x.adults,0),
   children:r.reduce((n,x)=>n+x.child_ages.length,0),
   rooms:r.length};
 }
 function serialize(rooms){
  const r=normalize(rooms);
  if(!r)throw Error("INVALID_TRAVELER_PARTY");
  return r.map(x=>x.adults+":"+x.child_ages.join(",")).join("|");
 }
 function parse(input){
  if(typeof input!=="string"||input.length>150||!input)return null;
  const groups=input.split("|");if(groups.length>MAX_ROOMS)return null;
  const rooms=[];
  for(const group of groups){
   const m=/^([1-9]|1[0-2]):((?:0|[1-9]|1[0-7])(?:,(?:0|[1-9]|1[0-7]))*)?$/.exec(group);
   if(!m)return null;
   rooms.push({adults:Number(m[1]),child_ages:m[2]?m[2].split(",").map(Number):[]});
  }
  const safe=normalize(rooms);
  return safe&&serialize(safe)===input?safe:null;
 }
 function fromQuery(params){
  if(!params||typeof params.get!=="function")return null;
  const encoded=params.get("rooms");
  if(encoded!==null){
   const rooms=parse(encoded),sum=totals(rooms);
   if(!sum)return null;
   if(params.has("adults")&&params.get("adults")!==String(sum.adults))return null;
   if(params.has("kids")&&params.get("kids")!==String(sum.children))return null;
   return rooms;
  }
  // Legacy links without child ages may display adult-only selections, but
  // never assume a child's age or construct a false provider quote.
  const adults=params.get("adults")||"2",kids=params.get("kids")||"0";
  if(!/^(?:[1-9]|1[0-2])$/.test(adults)||kids!=="0")return null;
  return normalize([{adults:Number(adults),child_ages:[]}]);
 }
 function suffix(rooms){
  const r=normalize(rooms),t=totals(r);
  if(!t)throw Error("INVALID_TRAVELER_PARTY");
  return "&adults="+t.adults+"&kids="+t.children+"&rooms="+encodeURIComponent(serialize(r));
 }
 function noun(n,one,few,many){
  const a=n%10,b=n%100;
  return b>=11&&b<=14?many:a===1?one:[2,3,4].includes(a)?few:many;
 }
 function roomLabel(room){
  const names=room.child_ages;
  return room.adults+" "+noun(room.adults,"взрослый","взрослых","взрослых")+
   (names.length?", "+names.length+" "+noun(names.length,"ребёнок","ребёнка","детей")+
    " ("+names.map(a=>a+" "+noun(a,"год","года","лет")).join(", ")+")":"");
 }
 function label(rooms){
  const r=normalize(rooms),t=totals(r);
  if(!t)return "Состав туристов не задан";
  return t.adults+" "+noun(t.adults,"взрослый","взрослых","взрослых")+
   (t.children?", "+t.children+" "+noun(t.children,"ребёнок","ребёнка","детей"):"")+
   " · "+r.length+" "+noun(r.length,"номер","номера","номеров")+
   (t.children?" · возраст детей: "+r.flatMap(x=>x.child_ages).join(", ")+" лет":"");
 }
 function description(rooms){
  const r=normalize(rooms);
  return r?r.map((g,i)=>"Номер "+(i+1)+": "+roomLabel(g)).join(" · "):"Неверный состав туристов";
 }
 function isTwoAdults(rooms){
  const r=normalize(rooms);return !!r&&r.length===1&&r[0].adults===2&&r[0].child_ages.length===0;
 }
 root.JamaicaTravelers=Object.freeze({normalize,totals,serialize,parse,fromQuery,suffix,
  roomLabel,label,description,isTwoAdults,MAX_ROOMS,MAX_ADULTS,MAX_CHILDREN,MAX_CHILD_AGE});
})(typeof window!=="undefined"?window:globalThis);

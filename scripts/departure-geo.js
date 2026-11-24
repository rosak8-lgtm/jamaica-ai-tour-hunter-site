(function(root){
"use strict";
const key="jamaica.departure.manual.v1";
function known(city,choices){return typeof city==="string"&&choices.includes(city);}
function endpoint(config){
 if(!config||config.schema!=="jamaica.departure-geo-config.v1"||config.enabled!==true||typeof config.endpoint!=="string")return null;
 try{
  const u=new URL(config.endpoint);
  return u.protocol==="https:"&&/^[a-z0-9-]+\.[a-z0-9-]+\.workers\.dev$/.test(u.hostname)&&
   !u.username&&!u.password&&!u.port&&!u.search&&!u.hash&&u.pathname==="/api/departure-city"?u.href:null;
 }catch{return null;}
}
function validHint(payload,choices){return payload?.schema==="jamaica.departure-hint.v1"&&payload.source==="IP_APPROXIMATE"&&known(payload.city,choices)?payload.city:null;}
async function start({select,status,apply,storage,fetcher=fetch,signal,canAuto=()=>true}){
 const choices=[...select.options].map(o=>o.value);
 let saved=null;
 try{saved=storage.getItem(key);}catch{}
 if(known(saved,choices)){if(canAuto()){apply(saved);status("Город сохранён по вашему выбору.");}return;}
 try{
  const configResponse=await fetcher("./departure-geo-config.json",{cache:"no-store",credentials:"omit",signal});
  if(!configResponse.ok)return;
  const url=endpoint(await configResponse.json());
  if(!url||!canAuto())return;
  const r=await fetcher(url,{cache:"no-store",credentials:"omit",redirect:"error",referrerPolicy:"no-referrer",signal});
  if(!r.ok||!canAuto())return;
  const city=validHint(await r.json(),choices);
  if(city&&canAuto()){apply(city);status("Предполагаемый город по IP. Можно изменить вручную.");}
 }catch{}
}
function remember(storage,city,choices){if(known(city,choices))try{storage.setItem(key,city);}catch{}}
root.JamaicaDepartureGeo={endpoint,validHint,start,remember,key};
})(typeof globalThis!=="undefined"?globalThis:window);

/* Offline JS acceptance: no passwords/DOBs sent from static site, no checkout. */
import fs from "node:fs";
import vm from "node:vm";
import assert from "node:assert/strict";

const html=fs.readFileSync("quote.html","utf8");
const inline=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(x=>x[1]).at(-1);
assert.ok(inline?.includes("/v1/party-price-checks"));
const previewId="p_"+"a".repeat(24);
const depart=new Date(Date.now()+21*86400000).toISOString().slice(0,10);

function element(){
 const flags=new Set(["hide"]);
 return {
  disabled:true, checked:false,textContent:"",
  listeners:{},
  classList:{
   add:c=>flags.add(c),
   remove:c=>flags.delete(c),
   contains:c=>flags.has(c),
  },
  addEventListener(name,fn){this.listeners[name]=fn;},
 };
}
function setup(rooms,config,priceReply){
 const els=Object.fromEntries([
  "quoteNotice","hotelTitle","tripSummary","checkQuote","quoteResult",
  "quotedPrice","quotedTerms","contractButton","onRequestAccept",
  "priceOnlyResult","priceOnlyValue","priceOnlyTerms",
 ].map(x=>[x,element()]));
 const requests=[];
 const T={
  fromQuery:()=>rooms,
  totals:()=>({adults:rooms.reduce((n,r)=>n+r.adults,0),
               children:rooms.reduce((n,r)=>n+r.child_ages.length,0)}),
  isTwoAdults:rs=>rs.length===1&&rs[0].adults===2&&rs[0].child_ages.length===0,
  label:()=>rooms.length+" номеров",
  description:()=>rooms.map(r=>r.adults+"+"+r.child_ages.join(",")).join("|"),
 };
 const preview={id:previewId,bookable:false,quote_verified:false,
  availability_verified:false,hotel:"TEST HOTEL",country:"Вьетнам",
  origin:"Иркутск",room:"STANDARD",nights:7,depart_date:depart};
 async function fetchMock(url,opts){
  requests.push({url:String(url),opts});
  if(String(url)==="./tour-previews.json")
   return {ok:true,json:async()=>({schema:"jamaica.tour-previews.v1",
                                    bookable:false,previews:[preview]})};
  if(String(url)==="./checkout-config.json")
   return {ok:true,json:async()=>config};
  return {ok:true,json:async()=>priceReply};
 }
 const location={search:"?preview="+previewId,assign:()=>{throw Error("Checkout not allowed");}};
 const ctx={window:{JamaicaTravelers:T,JamaicaCatalog:{findPreview:async()=>preview}},
  document:{getElementById:id=>els[id]},location,URL,URLSearchParams,
  sessionStorage:{getItem:()=>("x".repeat(48))},fetch:fetchMock,Intl};
 vm.runInNewContext(inline,ctx,{filename:"quote.html"});
 return {els,requests};
}
const config={schema:"jamaica.checkout-config.v1",price_checks_enabled:true,
 private_price_api_enabled:true,auth_api_enabled:true,
 live_booking_enabled:false,payments_enabled:false,
 contract_first_enabled:false,api_base_url:"https://price.jamaica.test/api"};
const rooms=[{adults:2,child_ages:[6,12]},{adults:1,child_ages:[4]}];
function supplierReply(override={}){
 return {
  status:"PRICE_ONLY_NOT_BOOKABLE",
  source_preview_id:previewId,
  total_rub:185000,currency:"RUB",groups_requested:2,
  supplier_total_scope:"WHOLE_TOUR",supplier_price_readonly:true,
  expires_at:new Date(Date.now()+180000).toISOString(),
  quote_verified:false,availability_verified:false,flight_verified:false,
  best_price_verified:false,bookable:false,booked:false,payment_enabled:false,
  ...override,
 };
}
async function tick(){await new Promise(r=>setImmediate(r));}

{
 const v=setup(rooms,config,supplierReply());
 await tick();
 assert.equal(v.els.checkQuote.disabled,false,
   "Multiroom parties should be able to request price-only when private API is configured");
 await v.els.checkQuote.listeners.click();
 assert.equal(v.requests.length,3);
 assert.equal(v.requests[2].url,"https://price.jamaica.test/api/v1/party-price-checks");
 assert.equal(v.requests[2].opts.method,"POST");
 assert.equal(v.requests[2].opts.credentials,"omit");
 const body=JSON.parse(v.requests[2].opts.body);
 assert.equal(body.preview_id,previewId);
 assert.equal(JSON.stringify(body.rooms),JSON.stringify(rooms));
 assert.deepEqual(Object.keys(body).sort(),["preview_id","rooms"]);
 assert.equal(v.els.priceOnlyResult.classList.contains("hide"),false);
 assert.match(v.els.priceOnlyValue.textContent,/185.000\s*₽ за весь состав/u);
 assert.equal(v.els.quoteResult.classList.contains("hide"),true);
 assert.equal(v.els.contractButton.disabled,true);
 assert.match(v.els.quoteNotice.textContent,/Бронь, договор и оплата не созданы/);
}
{
 const bads=[
  supplierReply({bookable:true}),
  supplierReply({quote_verified:true}),
  supplierReply({flight_verified:true}),
  supplierReply({groups_requested:1}),
  supplierReply({status:"QUOTE_READY"}),
  supplierReply({expires_at:new Date(Date.now()-1000).toISOString()}),
  supplierReply({total_rub:0}),
 ];
 for(const bad of bads){
  const v=setup(rooms,config,bad);
  await tick();
  await v.els.checkQuote.listeners.click();
  assert.equal(v.els.priceOnlyResult.classList.contains("hide"),true,
   "Never display untrusted or purchase-marked response");
  assert.equal(v.els.quoteResult.classList.contains("hide"),true);
  assert.match(v.els.quoteNotice.textContent,/Точная цена всего состава пока недоступна/);
 }
}
{
 for(const flag of ["price_checks_enabled","private_price_api_enabled","auth_api_enabled"]){
  const v=setup(rooms,{...config,[flag]:false},supplierReply());
  await tick();
  assert.equal(v.els.checkQuote.disabled,true,
   "An unconfigured private service must not get a working price button");
  assert.equal(v.requests.length,2);
 }
}
{
 const adults=[{adults:2,child_ages:[]}];
 const v=setup(adults,config,supplierReply({groups_requested:1}));
 await tick();
 assert.equal(v.els.checkQuote.disabled,false,
  "Price-only must also support two adults before live booking readiness");
 await v.els.checkQuote.listeners.click();
 assert.equal(v.els.quoteResult.classList.contains("hide"),true);
 assert.equal(v.els.priceOnlyResult.classList.contains("hide"),false);
}
console.log("JAMAICA private-only all-party price quote page: PASS");

import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const source=fs.readFileSync('scripts/catalog-shards.js','utf8');
new vm.Script(source,{filename:'catalog-shards.js'});
const existing=JSON.parse(fs.readFileSync('tour-previews.json','utf8'));
// A real 0-card feed is the ONLY correct production output while no bot
// receipt has passed BG best-price + both-green. Synthetic source records
// below exist ONLY in isolated Node tests, never in public JSON.
const model=existing.previews[0]||{
 id:'p_'+'a'.repeat(24),hotel_id:'102612345678',
 hotel:'OFFLINE_SYNTHETIC_TEST_HOTEL',country:'Вьетнам',
 origin:'Иркутск',resort:'Нячанг',room:'STANDARD AO',
 depart_date:'2026-12-25',nights:7,
 status:'REFERENCE_PRICE_LIST_ONLY',price_reference_rub:null,
 price_reference_party:'UNVERIFIED',
 bookable:false,quote_verified:false,
 availability_verified:false,flight_verified:false
};
assert.ok(model?.id?.startsWith('p_'),'Source-shard test fixture must be valid');
assert.ok(existing.previews.length>0||
 existing.publication_rule==='BG_ROUTE_FIRST_BEST_PRICE_BOTH_GREEN_V1',
 'No synthetic fixture may conceal a non-strict production feed');
const first={...model,id:'p_'+'1'.repeat(24)};
const second={...model,id:'p_'+'2'.repeat(24)};
const root={...existing,previews:[first],shards:[{
  path:'tour-previews-shards/part-001.json',count:1,sha256:'a'.repeat(64)
}],total_published_previews:2};
const part={schema:'jamaica.tour-preview-shard.v1',
  refreshed_at_utc:root.refreshed_at_utc,bookable:false,
  quote_verified:false,availability_verified:false,previews:[second]};
const files={'./tour-previews-shards/part-001.json':part};
let hits=0;
const context={window:{},fetch:async path=>{
 hits++;
 const data=files[path];
 return {ok:!!data,json:async()=>data};
}};
vm.runInNewContext(source,context,{filename:'catalog-shards.js'});
const catalog=context.window.JamaicaCatalog;
const historical={...first,status:'PREVIOUSLY_SEEN_NOT_RECHECKED',
  price_reference_rub:null,price_reference_party:'UNVERIFIED'};
assert.equal(catalog.validRow(historical),true,
 'An authentic earlier source can be listed without any price');
assert.equal(catalog.validRow({...historical,price_reference_rub:75000,
  price_reference_party:'TWO_ADULTS'}),false,
 'An unrechecked source can NEVER display last-cycle prices');
assert.equal(catalog.validRow({...historical,status:'UNKNOWN'}),false,
 'No unknown source status may be published');
assert.equal(catalog.manifest(root).length,1);
const checkpoints=[];
const rows=await catalog.allPreviews(root,(batch,done,total)=>{
  checkpoints.push({len:batch.length,done,total});
});
assert.equal(checkpoints[0].len,1,
 'Published root must render before waiting for optional source shards');
assert.equal(checkpoints[0].done,0);
assert.equal(checkpoints[checkpoints.length-1].done,1);
assert.equal(rows.length,2);
assert.equal(rows[1].id,second.id);
assert.equal((await catalog.findPreview(root,second.id)).hotel_id,model.hotel_id);
assert.equal((await catalog.findPreview(root,'p_'+'3'.repeat(24))),null);
assert.ok(hits>=2);
assert.equal((await catalog.allPreviews({...root,shards:undefined,
 total_published_previews:undefined})).length,1);
await assert.rejects(()=>catalog.allPreviews({...root,total_published_previews:3}),
 /UNSAFE_PUBLISHED_COUNT/);
await assert.rejects(()=>catalog.allPreviews({...root,shards:[{
 path:'../unsafe.json',count:1,sha256:'a'.repeat(64)}]}),
 /UNSAFE_SHARD_ENTRY/);
files['./tour-previews-shards/part-001.json']={...part,refreshed_at_utc:'2020-01-01T00:00:00Z'};
await assert.rejects(()=>catalog.allPreviews(root),/INCOMPLETE_SHARDED_CATALOG/);
files['./tour-previews-shards/part-001.json']={...part,previews:[first]};
await assert.rejects(()=>catalog.allPreviews(root),/DUPLICATE_SHARDED_PREVIEW/);
files['./tour-previews-shards/part-001.json']={...part,previews:[{...second,bookable:true}]};
await assert.rejects(()=>catalog.allPreviews(root),/INCOMPLETE_SHARDED_CATALOG/);

/* 13 sharded files must load in bounded parallel waves; previously three at
   a time held back more countries and made late-shard hotel lookups slow. */
const seven=Array.from({length:7},(_,i)=>({
  ...model,id:"p_"+(i+10).toString(16).padStart(24,"0")
}));
const wideParts=seven.map((_,i)=>({
  path:"tour-previews-shards/part-"+String(i+1).padStart(3,"0")+".json",
  count:1,sha256:"b".repeat(64)
}));
const wideRoot={...existing,previews:[first],shards:wideParts,
  total_published_previews:8};
const widePages=Object.fromEntries(wideParts.map((part,i)=>[
  "./"+part.path,{...part,count:undefined,
    schema:"jamaica.tour-preview-shard.v1",
    refreshed_at_utc:wideRoot.refreshed_at_utc,
    bookable:false,quote_verified:false,availability_verified:false,
    previews:[seven[i]]}
]));
let activeShards=0,maxActiveShards=0;
const wideContext={window:{},fetch:async path=>{
  activeShards++;
  maxActiveShards=Math.max(maxActiveShards,activeShards);
  await new Promise(resolve=>setTimeout(resolve,10));
  activeShards--;
  return {ok:!!widePages[path],json:async()=>widePages[path]};
}};
vm.runInNewContext(source,wideContext,{filename:"catalog-shards.js"});
const progress=[];
const expanded=await wideContext.window.JamaicaCatalog.allPreviews(
  wideRoot,(batch,done,total)=>progress.push([batch.length,done,total]));
assert.equal(maxActiveShards,6,"Use six bounded simultaneous shard fetches");
assert.deepEqual(progress,[[1,0,7],[7,6,7],[8,7,7]],
  "Country and hotel rows must become available before the last shard");
assert.equal(expanded.length,8);
assert.equal((await wideContext.window.JamaicaCatalog.findPreview(
  wideRoot,seven[6].id)).id,seven[6].id,
  "Tour deep in the catalog must remain addressable");

/* If a CDN shard fails, do not discard all other real countries in
   the same wave. Keep their safe rows, report partial coverage, retry the
   missing shard once, and still find tours in later successful shards. */
const firstShard="./tour-previews-shards/part-001.json";
let brokenCalls=0;
const brokenContext={window:{},fetch:async path=>{
 if(path===firstShard){
  brokenCalls++;
  return {ok:false,json:async()=>null};
 }
 return {ok:!!widePages[path],json:async()=>widePages[path]};
}};
vm.runInNewContext(source,brokenContext);
const incomplete=[];
await assert.rejects(()=>brokenContext.window.JamaicaCatalog.allPreviews(
 wideRoot,(batch,done,total)=>incomplete.push([batch.length,done,total])),
 /INCOMPLETE_SHARDED_CATALOG/);
assert.equal(brokenCalls,2,'Retry a failed CDN shard exactly once');
assert.deepEqual(incomplete,[[1,0,7],[6,6,7],[7,7,7]],
 'Other independently validated countries must survive one failed shard');
assert.equal((await brokenContext.window.JamaicaCatalog.findPreview(
 wideRoot,seven[6].id)).id,seven[6].id,
 'A good later-shard tour should still open despite an earlier missing shard');
await assert.rejects(()=>brokenContext.window.JamaicaCatalog.findPreview(
 wideRoot,"p_"+'f'.repeat(24)),/INCOMPLETE_SHARDED_CATALOG/,
 'An incomplete catalog cannot honestly claim that an absent tour does not exist');
let transientCalls=0;
const transient={window:{},fetch:async path=>{
 if(path===firstShard&&transientCalls++===0)
  return {ok:false,json:async()=>null};
 return {ok:!!widePages[path],json:async()=>widePages[path]};
}};
vm.runInNewContext(source,transient);
assert.equal((await transient.window.JamaicaCatalog.allPreviews(wideRoot)).length,8,
 'Transient CDN errors must heal without a page reload');
assert.equal(transientCalls,2);

console.log('JAMAICA_SHARDED_60000_LOADER_TEST_PASS');

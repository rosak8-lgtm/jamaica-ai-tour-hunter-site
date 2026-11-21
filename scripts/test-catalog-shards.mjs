import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const source=fs.readFileSync('scripts/catalog-shards.js','utf8');
new vm.Script(source,{filename:'catalog-shards.js'});
const existing=JSON.parse(fs.readFileSync('tour-previews.json','utf8'));
const model=existing.previews[0];
assert.ok(model?.id?.startsWith('p_'),'Real source-backed preview fixture required');
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
assert.equal(catalog.manifest(root).length,1);
const rows=await catalog.allPreviews(root);
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
await assert.rejects(()=>catalog.allPreviews(root),/CATALOG_SHARD_MISMATCH/);
files['./tour-previews-shards/part-001.json']={...part,previews:[first]};
await assert.rejects(()=>catalog.allPreviews(root),/DUPLICATE_SHARDED_PREVIEW/);
files['./tour-previews-shards/part-001.json']={...part,previews:[{...second,bookable:true}]};
await assert.rejects(()=>catalog.allPreviews(root),/CATALOG_SHARD_MISMATCH/);
console.log('JAMAICA_SHARDED_60000_LOADER_TEST_PASS');

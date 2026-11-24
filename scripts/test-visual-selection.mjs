import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const context={Date,Map,Object,Array,Number};
vm.createContext(context);
vm.runInContext(fs.readFileSync('scripts/visual-selection.js','utf8'),context);
const parsed=context.JamaicaVisualSelection;
assert.ok(parsed&&parsed.TTL===900000);
const now=Date.now();
const id='p_'+'a'.repeat(24);
const feed=(entry)=>({schema:'jamaica.visual-selection.v1',bookable:false,
 quote_verified:false,availability_verified:false,entries:[entry]});
const good={preview_id:id,observed_at_utc:new Date(now-1000).toISOString(),
 route_best_price_seen:true,both_green_planes_seen:true};
assert.equal(parsed.read(feed(good),now).size,1);
assert.equal(parsed.read(feed({...good,both_green_planes_seen:false}),now).size,0);
assert.equal(parsed.read(feed({...good,route_best_price_seen:false}),now).size,0);
assert.equal(parsed.read(feed({...good,observed_at_utc:new Date(now-910000).toISOString()}),now).size,0);
assert.equal(parsed.read(feed({...good,preview_id:'bad'}),now).size,0);
assert.equal(parsed.read({...feed(good),bookable:true},now).size,0);
assert.equal(parsed.read({...feed(good),quote_verified:true},now).size,0);
assert.equal(parsed.read({...feed(good),entries:[good,good]},now).size,0);
assert.equal(parsed.read({...feed(good),entries:[{...good,browser_session_digest:'SECRET'}]},now).size,0);
const thousand=Array.from({length:1000},(_,i)=>({...good,preview_id:'p_'+i.toString(16).padStart(24,'0')}));
assert.equal(parsed.MAX,1000);
assert.equal(parsed.read({...feed(good),entries:thousand},now).size,1000);
assert.equal(parsed.read({...feed(good),entries:[...thousand,{...good}]},now).size,0);
assert.equal(parsed.read({...feed(good),entries:thousand},now+16*60*1000).size,0);
const page=fs.readFileSync('index.html','utf8');
const visual=JSON.parse(fs.readFileSync('tour-visual-evidence.json','utf8'));
assert.equal(visual.schema,'jamaica.visual-selection.v1');
assert.ok(Array.isArray(visual.entries)&&visual.entries.length<=1000,
 "Publisher may deliver genuine route-first bot receipts when available");
assert.ok(visual.entries.every(x=>x.route_best_price_seen===true&&
 x.both_green_planes_seen===true&&/^p_[a-f0-9]{24}$/.test(x.preview_id)),
 "Every published visual receipt must contain both required checks");
assert.equal(visual.bookable,false);
assert.ok(page.includes('id="visualProofOnly"')&&
 page.includes('id="visualProofNotice"')&&
 page.includes('scripts/visual-selection.js')&&
 page.includes('window.JamaicaPublicVisualPolicy.eligible(x,visualProofs)')&&
 page.includes('loadVisualProofs();'));
assert.ok(page.includes('Карта')||page.includes('Страны')||page.includes('страны'),
 'Never delete broad country discovery UI');
console.log('JAMAICA_VISUAL_BOT_PUBLIC_SIDE_CAR_TEST_PASS');

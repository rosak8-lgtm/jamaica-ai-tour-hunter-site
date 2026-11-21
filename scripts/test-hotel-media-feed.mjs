import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const script=fs.readFileSync('scripts/hotel-media-feed.js','utf8');
new vm.Script(script);
const entry={
 hotel_name:'BASAYA BEACH HOTEL & RESORT',country:'Таиланд',
 rights_verified:true,commercial_publication_allowed:true,
 permission_reference:'LICENSE_DEMONSTRATION_VERIFIED',rights_verified_at:'2026-11-21',
 rights_expires_at:'2099-12-31',approved_image_hosts:['photos.hotelbeds.com'],
 approved_source_hosts:['photos.hotelbeds.com'],
 photos:[{src:'https://photos.hotelbeds.com/giata/bigger/a.jpg',
 source:'https://photos.hotelbeds.com/giata/a.jpg',
 license:'contract-authorized',credit:'Test verified supplier',kind:'other',
 alt:'Фото настоящего проверенного отеля'}]
};
const mediaIndex={schema:'jamaica.hotel-media-feed-index.v1',total_hotels:1,
 entries:{'102623766108':'hotel-media-feed/part-0001.json'}};
let calls=0;
const fixture={
 './hotel-media-feed/index.json':mediaIndex,
 './hotel-media-feed/part-0001.json':{
  schema:'jamaica.hotel-media-feed-part.v1',
  hotels:{'102623766108':entry}
 }
};
const sandbox={window:{},fetch:async url=>{calls++;return {
 ok:!!fixture[url],json:async()=>fixture[url]};},Date};
vm.runInNewContext(script,sandbox);
const photos=sandbox.window.JamaicaHotelMedia;
const e=await photos.getApprovedEntry('102623766108','Таиланд','BASAYA BEACH HOTEL & RESORT');
assert.equal(e.photos[0].src,entry.photos[0].src);
assert.equal(calls,2);
assert.equal(await photos.getApprovedEntry('102623766108','Таиланд','BASAYA BEACH HOTEL & RESORT'),e);
assert.equal(calls,2,'Do not refetch the photo shard on every search result');
assert.equal(await photos.getApprovedEntry('102623766108','Китай','BASAYA BEACH HOTEL & RESORT'),null);
assert.equal(await photos.getApprovedEntry('102623766108','Таиланд','Some Other Hotel'),null);
assert.equal(await photos.getApprovedEntry('../etc/passwd','Таиланд','BASAYA BEACH HOTEL & RESORT'),null);
fixture['./hotel-media-feed/part-0001.json'].hotels['102623766108']={...entry,rights_expires_at:'2020-01-01'};
assert.equal(await photos.getApprovedEntry('102623766108','Таиланд','BASAYA BEACH HOTEL & RESORT'),null);
console.log('JAMAICA_LICENSED_HBX_HOTEL_MEDIA_BROWSER_LOADER_PASS');

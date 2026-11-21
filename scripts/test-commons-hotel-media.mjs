import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync('scripts/commons-hotel-media.js','utf8');
new vm.Script(source);
const id='102623766108',name='BASAYA BEACH HOTEL & RESORT',country='Таиланд';
const file='Basaya Beach Hotel - Verified Exterior.jpg';
const photo={
 file,kind:'hotel_property',wikidata_qid:'Q123456',
 src:'https://commons.wikimedia.org/wiki/Special:FilePath/'+encodeURIComponent(file)+'?width=500',
 source:'https://commons.wikimedia.org/wiki/File:'+encodeURIComponent(file.replaceAll(' ','_')),
 license:'CC BY-SA 4.0',
 license_url:'https://creativecommons.org/licenses/by-sa/4.0/',
 author:'Verified photographer',alt:'Фотография гостиницы Basaya Beach Hotel & Resort'
};
const entry={
  hotel_name:name,country,wikidata_qid:'Q123456',
  identity_reviewed:true,
  identity_review_reference:'https://www.wikidata.org/wiki/Q123456',
  photos:[photo]
};
const index={schema:'jamaica.hotel-open-media-index.v1',total_hotels:1,
 entries:{[id]:'hotel-open-media/part-0001.json'}};
const part={schema:'jamaica.hotel-open-media-part.v1',hotels:{[id]:entry}};
const files={'./hotel-open-media/index.json':index,
 './hotel-open-media/part-0001.json':part};
let loads=0;
const sandbox={
 window:{},
 Date,URL,
 fetch:async url=>{loads++;const data=files[url];
   return {ok:!!data,json:async()=>data};}
};
vm.runInNewContext(source,sandbox);
const media=sandbox.window.JamaicaOpenHotelMedia;
assert.equal(media.photoOK(photo),true);
assert.equal(media.photoOK({...photo,src:photo.src.replace("?width=500","?width=720")}),false,
  'Custom width 720 must not be introduced again because it is CDN-throttled');
assert.equal((await media.get(id,country,name)).length,1);
assert.equal(loads,2);
assert.equal((await media.get(id,country,name))[0].src,photo.src);
assert.equal(loads,2,'Never refetch existing hotel photo shard per card');
assert.equal(await media.get(id,'Китай',name),null);
assert.equal(await media.get(id,country,'Other Hotel'),null);
assert.equal(await media.get('../../etc',country,name),null);
assert.equal(media.photoOK({...photo,license:'CC BY-NC 4.0'}),false);
assert.equal(media.photoOK({...photo,license_url:'https://evil.example/'}),false);
assert.equal(media.photoOK({...photo,src:'https://evil.example/photo.jpg'}),false);
assert.equal(media.photoOK({...photo,source:'https://commons.wikimedia.org/wiki/File:Other_Hotel.jpg'}),false);
assert.equal(media.photoOK({...photo,author:''}),false);
assert.equal(media.photoOK({...photo,file:'../../evil.jpg'}),false);
assert.equal(media.photoOK({...photo,wikidata_qid:'INVALID'}),false);
assert.equal(media.photoOK({...photo,kind:'country_scenery'}),false);
part.hotels[id]={...entry,identity_reviewed:false};
assert.equal(await media.get(id,country,name),null);
console.log('JAMAICA_WIKIMEDIA_COMMERCIALLY_LICENSED_PROPERTY_PHOTOS_PASS');

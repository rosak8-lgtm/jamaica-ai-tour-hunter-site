import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const page=fs.readFileSync('index.html','utf8');
const detail=fs.readFileSync('tour.html','utf8');
const checkout=fs.readFileSync('checkout.html','utf8');
const feed=JSON.parse(fs.readFileSync('verified-offers.json','utf8'));
const config=JSON.parse(fs.readFileSync('checkout-config.json','utf8'));
const data=page.match(/<script id="countries-data" type="application\/json">([\s\S]*?)<\/script>/);
assert.ok(data,'Country data must exist');
const countries=JSON.parse(data[1]);
assert.equal(countries.length,251);
assert.equal(countries.filter(c=>c.i).length,13);
assert.deepEqual(countries.slice(0,3).map(c=>c.n),['Таиланд','Китай','Вьетнам']);
assert.equal(new Set(countries.map(c=>c.n)).size,251);

const forbidden=/WhatsApp|wa\.me|mailto:|Библио-Глобус|библио-глобус|PEGAS|bgoperator/i;
for(const [name,source] of [['index',page],['tour',detail],['checkout',checkout]]){
 assert.ok(!forbidden.test(source),name+': no vendor branding or messenger');
 const scripts=[...source.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)]
   .map(x=>x[1]).filter(x=>x.includes('(function(){'));
 assert.equal(scripts.length,1,name+' script required');
 new vm.Script(scripts[0],{filename:name+'.js'});
}
for(const id of ['tourSearchForm','departure','destination','dateFrom','nights','adults','kids','budget','hotelSearch','countryDatalist','destinationGrid','destSearch','offerCards','offerCount']){
 assert.ok(page.includes('id="'+id+'"'),'Missing search control: '+id);
}
assert.ok(page.includes('value="0" selected>Любая длительность'));
assert.ok(page.includes('slice(visible,visible+300)'),'All 251 countries must be rendered');
assert.ok(page.includes('tour.html?offer='));
assert.ok(!page.includes('button.href="checkout.html?offer="'));
assert.ok(page.includes('setInterval(loadOffers,60000)'));
for(const id of ['hotelHero','hotelHeading','hotelSpecs','flightDetails','packageDetails','cancellationTerms','summary','tourPrice','checkoutLink']){
 assert.ok(detail.includes('id="'+id+'"'),'Tour details missing: '+id);
}
assert.ok(detail.includes('checkout.html?offer='));
assert.ok(detail.includes('photos_licensed===true'));
assert.ok(detail.includes('verified-offers.json'));
assert.equal(feed.schema,'jamaica.verified-offers.v1');
assert.ok(Array.isArray(feed.offers)&&feed.offers.length===0,'No invented available tours');
assert.equal(config.live_booking_enabled,false);
assert.equal(config.payments_enabled,false);
assert.equal(config.api_base_url,'');
for(const flag of ['quote_verified','flights_out_green','flights_back_green','availability_verified','total_two_verified','price_scope_verified','publish_approved']){
 assert.ok(page.includes('o.'+flag+'!==true'),'Index missing gate '+flag);
 assert.ok(detail.includes('"'+flag+'"'),'Details missing gate '+flag);
 assert.ok(checkout.includes('o.'+flag+'!==true'),'Checkout missing gate '+flag);
}

function functionFrom(source,signature){
 const start=source.indexOf(signature);
 assert.ok(start>=0,'Function missing '+signature);
 const match=source.slice(start).match(/^[\s\S]*?^\}/m);
 assert.ok(match,'Function body not found '+signature);
 return vm.runInNewContext('('+match[0]+')',{
   now:Date.now(),countries,Date,Number,Array,Object,String,RegExp,
   dataSafe:s=>typeof s==='string'?s.trim():''
 });
}
const now=Date.now();
const sample={
 id:'tour_abcdefgh123',origin:'Иркутск',destination:'Таиланд',hotel:'Test Hotel (CI only)',
 depart_date:new Date(now+3*86400000).toISOString().slice(0,10),
 nights:10,adults:2,children:0,total_rub:94500,
 quote_verified_at:new Date(now-60000).toISOString(),expires_at:new Date(now+300000).toISOString(),
 quote_verified:true,availability_verified:true,flights_out_green:true,flights_back_green:true,
 price_scope_verified:true,total_two_verified:true,publish_approved:true
};
const valid=functionFrom(detail,'function valid(o){');
assert.equal(valid(sample),true,'A truly confirmed tour must open hotel details');
assert.equal(valid({...sample,flights_back_green:false}),false);
assert.equal(valid({...sample,expires_at:new Date(now-1000).toISOString()}),false);
const strictOffer=functionFrom(page,'function strictOffer(o,now){');
assert.equal(strictOffer(sample,now),true,'A current confirmed quote must appear in search');
assert.equal(strictOffer({...sample,quote_verified:false},now),false);
const matching=functionFrom(page,'function matching(o,q){');
const q={origin:'Иркутск',country:'',date:'',nights:0,adults:2,children:0,budget:0,hotel:''};
assert.equal(matching(sample,q),true,'Any duration must show verified quotes');
assert.equal(matching(sample,{...q,nights:7}),false);
assert.equal(matching(sample,{...q,nights:10}),true);
assert.equal(matching(sample,{...q,country:'Таиланд'}),true);
assert.equal(matching(sample,{...q,country:'Китай'}),false);
assert.equal(matching(sample,{...q,hotel:'TEST HOTEL'}),true);
assert.equal(matching(sample,{...q,budget:30000}),false);
assert.equal(matching(sample,{...q,budget:50000}),true);
console.log('JAMAICA_TOUR_DETAILS_QA_PASS 251 countries, no 7-night default, quote -> detail -> checkout, no fake offers');

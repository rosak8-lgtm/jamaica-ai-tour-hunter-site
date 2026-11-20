import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const page=fs.readFileSync('index.html','utf8');
const feed=JSON.parse(fs.readFileSync('verified-offers.json','utf8'));
const match=page.match(/<script id="countries-data" type="application\/json">([\s\S]*?)<\/script>/);
assert.ok(match,'Country directory is required');
const countries=JSON.parse(match[1]);
assert.equal(countries.length,251,'251 readable destinations; invalid country placeholder excluded');
assert.equal(countries.filter(c=>c.i).length,13);
assert.equal(new Set(countries.map(c=>c.n)).size,countries.length);
assert.ok(countries.every(c=>typeof c.n==='string' && c.n.length>=3));
assert.deepEqual(countries.slice(0,3).map(c=>c.n),['Таиланд','Китай','Вьетнам']);
assert.ok(!/Библио-Глобус|библио-глобус|PEGAS|туроператор|bgoperator/i.test(page),'No supplier names in customer interface');
for(const id of ['leadForm','departure','destination','dateFrom','nights','adults','kids','budget','comment','countryDatalist','destinationGrid','destSearch','offerCards','emailLead']){
 assert.ok(page.includes('id="'+id+'"'),'Missing user-facing control: '+id);
}
assert.ok(page.includes('wa.me/995555516420'));
assert.ok(page.includes('mailto:yurii@monardas.com'));
assert.ok(page.includes('verified-offers.json'));
assert.ok(page.includes('quote_verified===true'));
assert.ok(page.includes('flights_out_green===true'));
assert.ok(page.includes('flights_back_green===true'));
assert.ok(page.includes('availability_verified===true'));
assert.ok(page.includes('total_two_verified===true'));
assert.ok(page.includes('Оплата на этом сайте не принимается.'));
assert.equal(feed.schema,'jamaica.verified-offers.v1');
assert.ok(Array.isArray(feed.offers));
assert.equal(feed.offers.length,0,'No unconfirmed inventory on a static site');
const js=[...page.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(x=>x[1]).filter(x=>x.includes('(function(){'));
assert.equal(js.length,1);
new vm.Script(js[0],{filename:'jamaica-client.js'});
console.log('JAMAICA_PUBLIC_QA_PASS: 251 destinations, 13 Irkutsk, sales lead form, JS syntax, no vendor branding, verified-offer gates');

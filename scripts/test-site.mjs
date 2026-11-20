import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const page=fs.readFileSync('index.html','utf8');
const checkout=fs.readFileSync('checkout.html','utf8');
const feed=JSON.parse(fs.readFileSync('verified-offers.json','utf8'));
const config=JSON.parse(fs.readFileSync('checkout-config.json','utf8'));
const match=page.match(/<script id="countries-data" type="application\/json">([\s\S]*?)<\/script>/);
assert.ok(match,'Country directory is required');
const countries=JSON.parse(match[1]);
assert.equal(countries.length,251,'251 valid countries; one invalid placeholder excluded');
assert.equal(countries.filter(c=>c.i).length,13);
assert.equal(new Set(countries.map(c=>c.n)).size,countries.length);
assert.ok(countries.every(c=>typeof c.n==='string' && c.n.length>=3));
assert.deepEqual(countries.slice(0,3).map(c=>c.n),['Таиланд','Китай','Вьетнам']);

const forbidden=/WhatsApp|wa\.me|mailto:|Библио-Глобус|библио-глобус|PEGAS|bgoperator/i;
assert.ok(!forbidden.test(page),'No messages, e-mail lead funnel or supplier names in public storefront');
assert.ok(!forbidden.test(checkout),'No messages, e-mail lead funnel or supplier names in checkout');
for(const id of ['tourSearchForm','departure','destination','dateFrom','nights','adults','kids','budget','hotelSearch','countryDatalist','destinationGrid','destSearch','offerCards','offerCount']){
 assert.ok(page.includes('id="'+id+'"'),'Missing on-site search control: '+id);
}
assert.ok(!page.includes('id="leadForm"'));
assert.ok(!page.includes('id="emailLead"'));
assert.ok(page.includes('verified-offers.json'));
assert.ok(page.includes('checkout.html?offer='));
for(const flag of ['quote_verified','flights_out_green','flights_back_green','availability_verified','total_two_verified','price_scope_verified','publish_approved']){
 assert.ok(page.includes('o.'+flag+'!==true'),'Missing strict quote gate: '+flag);
 assert.ok(checkout.includes('o.'+flag+'!==true'),'Missing checkout validation: '+flag);
}
assert.equal(feed.schema,'jamaica.verified-offers.v1');
assert.ok(Array.isArray(feed.offers));
assert.equal(feed.offers.length,0,'No fabricated inventory; no unofficial quotes');
assert.equal(config.schema,'jamaica.checkout-config.v1');
assert.equal(config.live_booking_enabled,false,'Booking blocked until real operator order API');
assert.equal(config.payments_enabled,false,'Payments blocked until verified merchant acquiring');
assert.equal(config.api_base_url,'','No fabricated API endpoint');
assert.ok(checkout.includes('checkout-config.json'));
assert.ok(checkout.includes('payment_iframe_origin'));
assert.ok(checkout.includes('PAID_BOOKED'));
assert.ok(checkout.includes('server') || checkout.includes('сервер'));
assert.ok(!checkout.match(/<input[^>]+name=["'](?:card|cvc|cvv|pan)/i),'Do not collect raw card details');
assert.ok(checkout.includes('checkoutForm'));
assert.ok(checkout.includes('termsAccept'));

for(const [name,source] of [['jamaica-search',page],['jamaica-checkout',checkout]]){
 const scripts=[...source.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(x=>x[1]).filter(x=>x.includes('(function(){'));
 assert.equal(scripts.length,1,name+': exactly one app script');
 new vm.Script(scripts[0],{filename:name+'.js'});
}
console.log('JAMAICA_SEARCH_CHECKOUT_QA_PASS 251 countries, 13 Irkutsk, no WhatsApp, no fictitious offers or payments, JS syntax verified');

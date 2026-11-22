import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const page=fs.readFileSync('index.html','utf8');
const detail=fs.readFileSync('tour.html','utf8');
const checkout=fs.readFileSync('checkout.html','utf8');
const account=fs.readFileSync('account.html','utf8');
const quotePage=fs.readFileSync('quote.html','utf8');
const previewSelection=fs.readFileSync('preview.html','utf8');
const feed=JSON.parse(fs.readFileSync('verified-offers.json','utf8'));
const config=JSON.parse(fs.readFileSync('checkout-config.json','utf8'));
/* JAMAICA-only modern aggregator-style search layout regressions */
const searchStyle=fs.readFileSync('assets/jamaica-search-ui.css','utf8');
const detailStyle=fs.readFileSync('assets/jamaica-detail-ui.css','utf8');
assert.ok(page.includes('./assets/jamaica-search-ui.css'));
assert.ok(page.includes('class="utilityBar"')&&page.includes('class="searchModeTabs"'));
assert.ok(page.includes('class="fields fieldsMain"'));
assert.ok(page.includes('id="advancedFilters"')&&page.includes('id="budget"'));
assert.ok(page.includes('class="resultsLayout"')&&page.includes('id="filtersDisclosure"'));
for(const filter of ['filterCountry','filterResort','filterNights','filterHotel',
  'filterBudget','filterApply','filterReset','favoritesOnly','favoritesCount']){
 assert.ok(page.includes('id="'+filter+'"'),'Missing functional search filter '+filter);
}
assert.ok(page.includes('sourceFilterOptions()')&&page.includes('applyTourSidebar()'),
  'Search sidebar cannot be a decorative mockup');
assert.ok(page.includes('id="otherCountries"')&&page.includes('id="catalogBreadth"'),
 'Customer must easily discover other published countries');
assert.ok(page.includes('availableCountries.slice(0,7)')&&page.includes('interleaveCountries(list)'),
 'Search must interleave actual countries without inventing availability');
const mascotAsset=fs.readFileSync('assets/jamaica-parrot-mascot.svg','utf8');
const mascotMark=fs.readFileSync('assets/jamaica-parrot-mark.svg','utf8');
for(const a of [mascotAsset,mascotMark]){
 assert.ok(a.startsWith('<svg ')&&a.includes('viewBox=')&&a.includes('stroke='));
 assert.ok(!/<(?:script|foreignObject)\b|(?:xlink:)?href=["']https?:\/\/|url\(\s*https?:\/\//i.test(a),
  'Mascot SVG must remain standalone without external scripts or remote images');
}
assert.ok(page.includes('src="./assets/jamaica-parrot-mascot.svg"')&&
 page.includes('src="./assets/jamaica-parrot-mark.svg"'),
 'Logo and hero must use the new glasses macaw');
assert.ok(searchStyle.includes('.heroArt .mascotHero')&&
 searchStyle.includes('.heroArt::after{display:none!important}'),
 'Old stick-like hero overlay must be gone');
for(const name of ['hotel.html','preview.html','tour.html','quote.html','checkout.html','account.html','route.html']){
 assert.ok(fs.readFileSync(name,'utf8').includes('src="./assets/jamaica-parrot-mark.svg"'),
  'Consistent customer pages: '+name);
}

assert.ok(page.includes('if(formCountry&&!countryCounts.has(formCountry))countryOptions.push({'),
 'The selected country must survive an empty current feed');
assert.ok(page.includes('id="budgetNotice"')&&page.includes('budgetNotice").textContent=budgetMessage'),
 'Traveler must be informed when a budget cannot be applied');
assert.ok(page.includes('referencePrice(x)!==null&&')&&page.includes('referencePrice(x)<=budget*2'),
 'A selected budget may only match known prices for two adults');
assert.ok(!page.includes('!budget||!partyTwoAdults||referencePrice(x)===null'),
 'Unknown-price offers must not masquerade as within budget');
assert.ok(!page.includes('онлайн-бронирование туров</title>'),
 'SEO must not promise unconfigured booking');

assert.ok(page.includes('const card=el("article","offerCard tourResultCard")'));
assert.ok(page.includes('favoriteIds.has(x.id)')&&page.includes('localStorage.setItem('));
assert.ok(page.includes('Цена пока не подтверждена;'),
 'Never imply a price or supplier booking where neither is verified');
assert.ok(searchStyle.includes('.tourResultCard')&&searchStyle.includes('.fieldsMain'));
assert.ok(searchStyle.includes('@media(max-width:580px)'),
 'Mobile travel search layout is required');
assert.ok(!searchStyle.includes('url(http'),'No external potentially unlicensed photos');
assert.equal(config.live_booking_enabled,false,'Cannot fake live supplier bookings');
assert.equal(config.payments_enabled,false,'Cannot fake secure live payments');

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
for(const id of ['tourSearchForm','departure','destination','dateFrom','nights','adults','kids','budget','hotelSearch','countryDatalist','offerCards','offerCount']){
 assert.ok(page.includes('id="'+id+'"'),'Missing search control: '+id);
}
assert.ok(page.includes('value="0" selected>Любая длительность'));
assert.ok(page.includes('id="dateTo"'),'Date-to filter is required for monthly searching');
assert.ok(page.includes('for(let n=3;n<=180;n++)'),'Every supported 3–180-night length must be selectable');
assert.ok(page.includes('(!date||x.depart_date>=date)&&(!dateTo||x.depart_date<=dateTo)'),
 'Preview results must respect the inclusive date interval');
assert.ok(page.includes('sampled_departure_months'),'Source-backed months sampled this cycle should be visible');
assert.ok(page.includes('Месяцы, из которых проверялись прайс-листы'),'Do not claim all months were checked');

assert.ok(!page.includes('id="destinations"'),'Do not put 251 empty country cards between search and real tours');
assert.ok(!page.includes('id="destinationGrid"'),'Country-card wall must be absent');
assert.ok(!page.includes('id="allCountrySelector"'),'Avoid redundant full country selector in results');
assert.ok(page.includes('for(const c of sorted){const e=document.createElement("option");e.value=c.n;datalist.append(e);}' ),
          'All 251 countries must still be available in search datalist');
assert.ok(page.indexOf('id="offers"')>page.indexOf('id="tourSearchForm"'),
          'Search results should directly follow the compact search');
assert.ok(page.indexOf('id="offers"')<page.indexOf('id="hotels"'),
          'Real offers have priority over additional hotel directory');
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
assert.equal(config.contract_first_enabled,false);
assert.equal(config.trusted_signature_enabled,false);
assert.equal(config.auth_api_enabled,false);
assert.ok(checkout.includes('/v1/contract-orders/draft'));
assert.ok(!checkout.includes('/v1/checkout/prepare'),'Legacy pay-before-contract route forbidden');
assert.ok(previewSelection.includes('quote.html?preview='));
assert.ok(quotePage.includes('/v1/preview-quotes'));
assert.ok(quotePage.includes('checkout.html?quote='));
assert.ok(account.includes('/verify-signature'));
assert.ok(account.includes('/payment'));
assert.ok(account.includes('PAID_RECHECK_REQUIRED'));
assert.ok(account.includes('BOOKING_RECONCILIATION_REQUIRED'));
for(const [name,source] of [['account',account],['quote',quotePage]]){
  assert.ok(!forbidden.test(source),'supplier branding: '+name);
  const scripts=[...source.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)]
      .map(m=>m[1]).filter(x=>x.includes('(function(){'));
  assert.equal(scripts.length,1);
  new vm.Script(scripts[0],{filename:name+'.js'});
}

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
   dataSafe:s=>typeof s==='string'?s.trim():'',
   referencePrice:x=>Number.isSafeInteger(x.price_reference_rub)&&x.price_reference_rub>0?x.price_reference_rub:null
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
const previewPriceSort=functionFrom(page,'function previewPriceCompare(a,b){');
const cheap={depart_date:'2026-12-10',country:'Таиланд',hotel:'A',price_reference_rub:51000};
const costly={depart_date:'2026-12-01',country:'Китай',hotel:'B',price_reference_rub:99000};
const unknown={depart_date:'2026-12-02',country:'Вьетнам',hotel:'C',price_reference_rub:null};
assert.ok(previewPriceSort(cheap,costly)<0,'Cheapest should rank before earliest date');
assert.ok(previewPriceSort(costly,unknown)<0,'Known reference price before unknown');
assert.ok(previewPriceSort(unknown,cheap)>0,'Unknown price never ranked as free or cheapest');
const matching=functionFrom(page,'function matching(o,q){');
const q={origin:'Иркутск',country:'',date:'',nights:0,adults:2,children:0,budget:0,hotel:''};
assert.equal(matching(sample,q),true,'Any duration must show verified quotes');
assert.equal(matching(sample,{...q,nights:7}),false);
assert.equal(matching(sample,{...q,nights:10}),true);
assert.equal(matching(sample,{...q,country:'Таиланд'}),true);
assert.equal(matching(sample,{...q,country:'Китай'}),false);
assert.equal(matching(sample,{...q,hotel:'test hotel'}),true,'Normalized hotel query');
assert.equal(matching(sample,{...q,budget:30000}),false);
assert.equal(matching(sample,{...q,budget:50000}),true);
assert.equal(matching(sample,{...q,date:sample.depart_date,dateTo:sample.depart_date}),true,
 'Both date endpoints must be inclusive');
assert.equal(matching(sample,{...q,date:'2099-01-01'}),false,
 'Future start date must exclude earlier tours');
assert.equal(matching(sample,{...q,dateTo:'2020-01-01'}),false,
 'Earlier end date must exclude later tours');

const guide=JSON.parse(fs.readFileSync('hotel-reference.json','utf8'));
const hotelPage=fs.readFileSync('hotel.html','utf8');
assert.ok(hotelPage.includes('./assets/jamaica-detail-ui.css'));
assert.ok(previewSelection.includes('./assets/jamaica-detail-ui.css'));
assert.ok(detailStyle.includes('.selectionLayout')&&detailStyle.includes('#gallery'));
assert.ok(hotelPage.indexOf('id="hotelPhotos"')<
  hotelPage.indexOf('id="hotelDescriptionSection"'),
  'Only verified property photos first, hotel source detail later');
assert.ok(previewSelection.includes('id="bookingPanel"'),
  'Tour price verification must remain prominent and truthful');

assert.equal(guide.schema,'jamaica.hotel-reference.v1');
assert.equal(guide.bookable,false);
assert.equal(guide.hotels.length,159,'Actual historic hotel names, no synthetic hotels');
assert.equal(guide.hotels.filter(x=>x.country==='Таиланд').length,79);
assert.equal(guide.hotels.filter(x=>x.country==='Китай').length,80);
assert.equal(guide.hotels.reduce((n,x)=>n+x.observation_count,0),2366);
assert.ok(guide.hotels.every(x=>x.bookable===false&&x.quote_verified===false&&x.availability_verified===false));
assert.ok(guide.hotels.every(x=>!('observed_amount_rub' in x)&&!('operator' in x)&&!('source_url' in x)));
assert.ok(!/WhatsApp|wa\.me|mailto:|Библио-Глобус|PEGAS|bgoperator/i.test(hotelPage));
assert.ok(page.includes('id="hotelGuideSearch"')&&page.includes('id="hotelGuideCards"'));
assert.ok(page.includes('hotel.html?id='));
assert.ok(page.includes('id="searchResultsCount"'),'Main results count must reflect real tour-source records');
assert.ok(page.indexOf('id="previewCards"')<page.indexOf('id="offerCards"'),
          'Actual price-list tour results must appear BEFORE zero confirmed-bookings widget');
assert.ok(page.includes('Подробнее об отеле, фото и отзывы'));
assert.ok(hotelPage.includes('hotel-reference.json'));
for(const id of ['gallery','description','rooms','trips','reviewList','reviewForm','reviewSubmit','reviewNotice']){
 assert.ok(hotelPage.includes('id="'+id+'"'),'Hotel page missing: '+id);
}
assert.ok(!hotelPage.includes('commons.wikimedia.org/w/api.php'),
          'Hotel gallery must not guess from text-only name matches');
assert.ok(!hotelPage.includes('upload.wikimedia.org'),
          'No broad country search for hotel media');
assert.ok(!hotelPage.includes('function photoSearchPlaceName('),
          'Destination media is forbidden in a specific hotel gallery');
assert.ok(hotelPage.includes('!["hotel_exterior","hotel_public_area"].includes(p.kind)'),
          'Only actual property photos enter gallery');
assert.ok(hotelPage.includes('showPhotoPlaceholder()'),
          'Missing hotel images produce an honest placeholder');
assert.ok(hotelPage.includes('tour-previews.json'),'Hotel detail must show real date and room references');
assert.ok(hotelPage.includes('hotel-reviews-config.json'),'Hotel review backend config required');
assert.ok(hotelPage.includes('hotel-media-approved.json'),'Supplier gallery needs explicit commercial-use grant');
assert.ok(page.includes('./scripts/commons-hotel-media.js'));
assert.ok(page.includes('window.JamaicaOpenHotelMedia.get('));
assert.ok(page.includes('Условия лицензии'));
assert.ok(hotelPage.includes('./scripts/commons-hotel-media.js'));
assert.ok(hotelPage.includes('loadOpenLicensedHotelPhotos()'));
assert.ok(hotelPage.includes('showVerifiedOfficialGallery()'));
assert.ok(hotelPage.includes('hotel-official-sites.json'));
assert.ok(hotelPage.includes('Фотографии выбранного отеля'));
const openIndex=JSON.parse(fs.readFileSync('hotel-open-media/index.json','utf8'));
assert.equal(openIndex.schema,'jamaica.hotel-open-media-index.v1');
assert.equal(openIndex.total_hotels,0,'Do not fabricate hotel identity matches');
assert.deepEqual(openIndex.entries,{});
const officialIndex=JSON.parse(fs.readFileSync('hotel-official-sites.json','utf8'));
assert.equal(officialIndex.schema,'jamaica.hotel-official-sites.v1');
assert.deepEqual(officialIndex.hotels,{});
const hotelPhotos=JSON.parse(fs.readFileSync('hotel-media-approved.json','utf8'));
assert.equal(hotelPhotos.schema,'jamaica.hotel-media-approved.v1');
assert.deepEqual(hotelPhotos.hotels,{},'Never publish unlicensed operator special-offer images');
const enriched=JSON.parse(fs.readFileSync('hotel-enrichment.json','utf8'));
assert.equal(enriched.hotels['102623766108'].rooms_total,'110');
assert.equal(enriched.hotels['102623766108'].photos.length,0);
assert.equal(enriched.hotels['102667206879'].photos.length,6,'Guangzhou hotel must have six verified CC4 photos');
assert.equal(enriched.hotels['102667206879'].photos.filter(p=>p.kind==='hotel_exterior').length,3);
assert.equal(enriched.hotels['102667206879'].photos.filter(p=>p.kind==='view_from_hotel').length,3);
assert.ok(enriched.hotels['102667206879'].photos.every(p=>p.license==='CC BY-SA 4.0'));
for(const [id,name,country,license,kind] of [
 ['102610001177','ROYAL CLIFF BEACH HOTEL','Таиланд','CC BY-SA 4.0','hotel_exterior'],
 ['102610001141','AMARI PATTAYA','Таиланд','CC BY-SA 4.0','hotel_exterior'],
 ['102616490643','INTERCONTINENTAL NHA TRANG','Вьетнам','CC BY-SA 3.0','hotel_exterior'],
 ['102667202290','GRAND HYATT SHANGHAI (上海金茂君悦大酒店)','Китай','CC BY 2.0','hotel_public_area']
]){
 const h=enriched.hotels[id];
 assert.ok(h&&h.name===name&&h.country===country, 'Exact hotel identity '+id);
 assert.ok(h.sources.every(s=>s.url.startsWith('https://commons.wikimedia.org/wiki/File:')));
 assert.equal(h.photos.length,1,'No extra unrelated scenery '+id);
 assert.equal(h.photos[0].license,license);
 assert.equal(h.photos[0].kind,kind);
 assert.equal(h.photos[0].source,
   'https://commons.wikimedia.org/wiki/File:'+h.photos[0].file.replaceAll(' ','_'));
}
assert.ok(hotelPage.includes('"CC BY 2.0":"https://creativecommons.org/licenses/by/2.0/"'),
 'Commercially reusable CC BY 2.0 hotel photo credit and license');

for(const [id,name,country,source] of [
 ['102618075164','BAIYUN HOTEL GUANGZHOU (广州白云宾馆)','Китай','Guangzhou Baiyun Hotel 20211210-03.jpg'],
 ['102624989868','CHINA HOTEL GUANGZHOU (广州中国大酒店 )','Китай','广州中国大酒店.jpg'],
 ['102625907920','КРАСНОЯРСК, гостиница','Россия','Гостиница "Красноярск".JPG']
]){
 const x=enriched.hotels[id];
 assert.ok(x&&x.name===name&&x.country===country,'Existing published tour exact-ID source '+id);
 assert.equal(x.photos.length,1);
 assert.equal(x.photos[0].file,source);
 assert.equal(x.photos[0].kind,'hotel_exterior');
 assert.equal(x.photos[0].license,'CC BY-SA 4.0');
}
assert.ok(page.includes('_.\" -]{5,170}')&&hotelPage.includes('_.\" -]{5,170}'),
 'Wikimedia filenames containing quotation marks must be safe and supported');
const remotePhotoUrlFn=hotelPage.match(/function strictExternalPhotoUrl\([\s\S]*?\n\}/);
assert.ok(remotePhotoUrlFn,'Required HTTPS exact-host safe remote image linking');
const strictExternalPhotoUrl=vm.runInNewContext(
 '('+remotePhotoUrlFn[0]+')',{URL});
const hosts=['cdn.partnerhotel.example'];
assert.equal(
 strictExternalPhotoUrl('https://cdn.partnerhotel.example/asia/pool.jpg',hosts,{image:true}),
 'https://cdn.partnerhotel.example/asia/pool.jpg');
for(const invalid of [
 'http://cdn.partnerhotel.example/asia/pool.jpg',
 'https://evil.example/asia/pool.jpg',
 'https://cdn.partnerhotel.example/asia/pool.jpg?jwt=secret',
 'https://user:pass@cdn.partnerhotel.example/asia/pool.jpg',
 'https://cdn.partnerhotel.example/asia/source.html',
 'javascript:alert(1)',
 'data:image/png;base64,test'
]){
 assert.equal(strictExternalPhotoUrl(invalid,hosts,{image:true}),null,invalid);
}

const reviewsConfig=JSON.parse(fs.readFileSync('hotel-reviews-config.json','utf8'));
assert.equal(reviewsConfig.schema,'jamaica.hotel-reviews.v1');
assert.equal(reviewsConfig.enabled,false,'Do not enable review POST until a real HTTPS backend exists');
assert.ok(!hotelPage.includes('checkout.html?offer='));
const hotelScripts=[...hotelPage.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(x=>x[1]).filter(x=>x.includes('(function(){'));
assert.equal(hotelScripts.length,1);
new vm.Script(hotelScripts[0],{filename:'hotel-reference.js'});

const directory=JSON.parse(fs.readFileSync('destination-directory.json','utf8'));
assert.equal(directory.schema,'jamaica.destination-directory.v1');
assert.equal(directory.availability_verified,false);
assert.equal(directory.quote_verified,false);
assert.equal(directory.total_countries,251);
assert.ok(directory.total_hotels>=1000,'Official hotel directory should not be the old 159 hotel archive');
assert.equal(directory.hotels.length,directory.total_hotels);
assert.ok(directory.hotels.every(h=>typeof h.name==='string'&&typeof h.country==='string'&&typeof h.id==='string'));
assert.ok(page.includes('destination-directory.json'),'Client must load the new global directory');
assert.ok(page.includes('window.jamaicaUpdateHotels'),'Search criteria must filter the hotel list');
assert.ok(page.includes('slice(visible,visible+48)'),'Large catalogue must be paginated');
assert.ok(hotelPage.includes('destination-directory.json'),'Hotel detail must use official hotel directory');
assert.ok(hotelPage.includes('destination-directory.json'),'Hotel detail must support official entries');
const routePage=fs.readFileSync('route.html','utf8');
const routeFeed=JSON.parse(fs.readFileSync('route-discovery.json','utf8'));
assert.equal(routeFeed.schema,'jamaica.route-discovery.v1');
assert.equal(routeFeed.bookable,false);
assert.equal(routeFeed.quote_verified,false);
assert.equal(routeFeed.availability_verified,false);
assert.ok(Array.isArray(routeFeed.routes));
const previews=JSON.parse(fs.readFileSync('tour-previews.json','utf8'));
assert.equal(previews.schema,'jamaica.tour-previews.v1');
assert.equal(previews.bookable,false);
assert.equal(previews.quote_verified,false);
assert.equal(previews.availability_verified,false);
assert.ok(Array.isArray(previews.previews)&&previews.previews.length<=8000);
assert.ok(previews.previews.every(x=>x.bookable===false&&x.quote_verified===false&&x.availability_verified===false));
assert.ok(page.includes('id="previewCards"'));
assert.ok(page.includes('function previewCardPhoto(x)'),'Preview cards need identity-verified hotel photo or honest placeholder');
assert.ok(page.includes('function curatedPreviewPhoto(x)'),'Use verified hotel-specific Commons photos where known');
assert.ok(!page.includes('function licensedDestinationScene(country)'),'Never mislabel country scenery as a hotel photo');
assert.ok(page.includes('async function renderDestinationPhoto(area,x,plain)') &&
 page.includes('destination_not_hotel') &&
 page.includes('Фото направления · не фото гостиницы'),
 'Destination photos may fill empty card visuals ONLY when clearly distinct from actual hotel photos');
const destinationMedia=JSON.parse(fs.readFileSync('assets/jamaica-destination-media.json','utf8'));
assert.equal(destinationMedia.schema,'jamaica.destination-media.v1');
assert.equal(Object.keys(destinationMedia.countries).length,13);
for(const [country,item] of Object.entries(destinationMedia.countries)){
 assert.equal(item.kind,'destination_not_hotel',country);
 assert.ok(item.author.length>=3&&/^CC BY(?:-SA)? (?:3\.0|4\.0)$/.test(item.license),country);
 assert.equal(item.source,'https://commons.wikimedia.org/wiki/File:'+item.file.replaceAll(' ','_'));
 assert.ok(item.license_url.startsWith('https://creativecommons.org/licenses/'));
}
for(const name of ['hero','logo']){
 const file=fs.readFileSync('assets/jamaica-parrot-'+name+'-v2.avif');
 assert.ok(file.length>1000&&file.length<60000&&
  file.toString('ascii',4,12)==='ftypavif','Real generated parrot image not deployed: '+name);
}
assert.ok(page.includes('srcset="./assets/jamaica-parrot-hero-v2.avif"')&&
 page.includes('srcset="./assets/jamaica-parrot-logo-v2.avif"'),
 'Real prepared mascot should appear in hero and top-left corner, not only as an SVG test asset');
for(const filename of ['hotel.html','preview.html','tour.html','quote.html','checkout.html','account.html','route.html']){
 assert.ok(fs.readFileSync(filename,'utf8').includes('srcset="./assets/jamaica-parrot-logo-v2.avif"'),
  'All customer pages must use the real mascot photo: '+filename);
}
assert.ok(!page.includes('countrySceneNames'),'Country imagery must not replace hotel pictures');
assert.ok(page.includes('async function approvedPartnerPreviewPhoto(x)'),'Allow only individually approved hotel CDN image feeds');
assert.ok(page.includes('e.rights_verified!==true'),'Hotel partner rights must be checked');
assert.ok(page.includes('img.referrerPolicy="no-referrer"'),'Do not leak referral context to photo host');
assert.ok(page.includes('Проверенная фотография гостиницы пока недоступна'),'Missing hotel photo should be disclosed');
assert.ok(!page.includes('landscape filetype:bitmap'),'Do not search scenery as hotel photographs');
assert.ok(page.includes('area.replaceChildren(plain)')&&page.includes('renderDestinationPhoto(area,x,fallback)'),
 'Broken images must fall back to labelled destination imagery or a plain placeholder');
assert.ok(page.includes('nextVerifiedPhoto()'),'Card must retry another rights-verified photo of the same hotel');
assert.ok(page.includes('fallbackSrc:alternate&&alternate!==src?alternate:null'),
  'Never retry an HTML attribution URL as an image');
assert.ok(page.includes('"?width=500"')&&page.includes('"?width=330"'),
  'Commons thumbnails must use Wikimedia-supported widths');
assert.ok(hotelPage.includes('img.src=fileUrl+"?width=960"')&&
          hotelPage.includes('img.src=fileUrl+"?width=500"'),
  'Hotel gallery should load actual IMG nodes and retry standard Commons size');
const commonsMediaScript=fs.readFileSync('scripts/commons-hotel-media.js','utf8');
assert.ok(commonsMediaScript.includes('"?width=500"'));
assert.ok(!commonsMediaScript.includes('"?width=720"'),'Do not revive throttled 720px Commons images');
const commonsLicenseFn=functionFrom(page,'function approvedCommonsLicense(raw){');
assert.equal(commonsLicenseFn('CC BY-SA 4.0'),'CC BY-SA 4.0');
assert.equal(commonsLicenseFn('CC BY 3.0'),'CC BY 3.0');
assert.equal(commonsLicenseFn('CC0 1.0'),'CC0 1.0');
assert.equal(commonsLicenseFn('All rights reserved'),null);
assert.equal(commonsLicenseFn('<b>CC BY-SA 4.0</b>'),null);

assert.ok(page.includes('id="previewMore"'));
assert.ok(page.includes('tour-previews.json'));
assert.ok(page.includes('function renderTourPreviews('));
assert.ok(!page.includes('id="previewCountryChips"'),'Do not cover tour results with full-country button wall');
assert.ok(page.includes('id="sourceDetails"'),'Keep source transparency available in a compact details section');
assert.ok(page.includes('id="previewCards"'),'Tour cards must remain the primary content');
assert.ok(page.indexOf('id="previewCards"')<page.indexOf('id="previewCoverage"'),
 'Actual offer cards must be above technical source diagnostics');
assert.ok(page.includes('href="#request">Изменить поиск</a>'),
 'All country choices belong to main search form');
assert.ok(!page.includes('function renderPreviewCountryChips()'),
 'No dynamic button wall for unsupported countries');
assert.ok(page.includes('function interleaveCountries(rows)'));
assert.ok(page.includes('function referencePrice(x)'));
assert.ok(page.includes('id="previewUpdatedAt"'));
assert.ok(page.includes('id="previewCoverage"'));
assert.ok(!page.includes('id="sourceCountryPriority"'),
 'Detailed country polling text must not displace offers');
assert.ok(page.includes('const priorities=new Map([["Таиланд",0],["Китай",1],["Вьетнам",2]])'),
 'Country priority remains in the search datalist');
assert.ok(!page.includes('id="allCountrySelector"'),"No duplicate country chooser in the results");
assert.ok(page.includes('fullCountryNames.length'));
assert.ok(page.includes('В текущей опубликованной выборке нет подходящих вариантов по направлению'),'Empty-state scope must stay honest');
assert.ok(page.includes('data.countries_status'));
assert.ok(page.includes('if(document.visibilityState==="visible")loadTourPreviews();'));
assert.ok(page.includes('5*60*1000'));
assert.ok(page.includes('price_reference_party'));
assert.ok(page.includes('previewPriceFresh'));
assert.ok(page.includes('Цена по прайс-листу на 2 взрослых'));
assert.ok(page.includes('if(!country&&!(sortMode==="price"&&partyTwoAdults))list=interleaveCountries(list)'));
assert.ok(page.includes('id="previewSort"'),'User-selectable tour sorting required');
assert.ok(page.includes('function previewPriceCompare(a,b)'),'Price comparator required');
assert.ok(page.includes('referencePrice(x)<=budget*2'),'Budget must honor 24-hour listed price, not 30-minute freshness');
assert.ok(!page.includes('currentReferencePrice(x)<=budget*2'),'Stale-price budget bug must not return');
assert.ok(page.includes('data.truncated_to_public_limit===true'),'Truncation must be visible');
assert.ok(page.includes('previewCandidateTotal.toLocaleString("ru-RU")'),'Candidate count needs visibility');

assert.ok(page.includes('preview.html?id='));
const previewDetail=fs.readFileSync('preview.html','utf8');
assert.ok(previewDetail.includes('price_reference_rub'));
assert.ok(previewDetail.includes('30*60*1000'));
for(const id of ['heading','subtitle','notice','facts','hotelInfo','hotelLink','bookingStatus','alternatives']){
 assert.ok(previewDetail.includes('id="'+id+'"'),'Preview detail missing '+id);
}
assert.ok(previewDetail.includes('tour-previews.json'));
assert.ok(previewDetail.includes('x.bookable===false'));
assert.ok(!/WhatsApp|wa\.me|mailto:|Библио-Глобус|PEGAS|bgoperator/i.test(previewDetail));
const previewScripts=[...previewDetail.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)]
 .map(x=>x[1]).filter(x=>x.includes('(function(){'));
assert.equal(previewScripts.length,1);
new vm.Script(previewScripts[0],{filename:'preview-details.js'});

// The route data still powers deep links, but its huge, non-bookable directory
// must not crowd the customer search page or create an extra network request.
assert.ok(!page.includes('id="routes"'),'Unbookable route wall must not be public');
assert.ok(!page.includes('id="routeCards"'),'No route cards under search results');
assert.ok(!page.includes('id="routeCountryChips"'),'No route-country chips under the offers');
assert.ok(!page.includes('loadRouteDiscovery();'),'Homepage must not fetch route directory');
assert.ok(page.includes('id="hotelDirectoryDisclosure"'),
  'Hotel reference remains reachable in an optional expandable section');
assert.ok(page.includes('if(location.hash==="#hotels")openHotelDirectory()'),
  'Direct hotel directory deep links must still work');
assert.ok(!page.includes('loadHotelReference();\nlet previewRecords='),
  'Full hotel reference must not load by default');
assert.ok(routePage.includes('destination-directory.json'));
assert.ok(routePage.includes('id="routePreviewSection"'));
assert.ok(routePage.includes('id="routePreviewList"'));
assert.ok(routePage.includes('id="routePreviewCount"'));
assert.ok(routePage.includes('p.depart_date===route.date'));
assert.ok(routePage.includes('preview.html?id='));

assert.ok(routePage.includes('route-discovery.json'));
for(const id of ['alternativeSection','alternativeCountry','alternativeNights','alternativeDate','alternativeCount','alternativeList','alternativeMore']){
 assert.ok(routePage.includes('id="'+id+'"'),'Route detail missing alternative control '+id);
}
assert.ok(routePage.includes('routes.routes.filter'),'Alternatives must come from actual route feed');
assert.ok(routePage.includes('x.bookable===false'),'Alternatives must not claim verified bookability');
assert.ok(routePage.includes('a.country===route.country?1:0')&&routePage.includes('b.country===route.country?1:0'),'Different countries should be prioritized');
assert.ok(routePage.includes('altMatches.slice(altVisible,altVisible+24)'),'Alternatives must be paginated');
assert.ok(!/WhatsApp|wa\.me|mailto:|Библио-Глобус|PEGAS|bgoperator/i.test(routePage));
const routeScripts=[...routePage.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(x=>x[1]).filter(x=>x.includes('(function(){'));
assert.equal(routeScripts.length,1);
new vm.Script(routeScripts[0],{filename:'jamaica-route.js'});
console.log('JAMAICA_GLOBAL_DIRECTORY_PASS countries='+directory.total_countries+' hotels='+directory.total_hotels);

console.log('JAMAICA_TOUR_DETAILS_QA_PASS 251 countries, 159 historical hotels, flexible search, offer -> tour -> checkout, no unsupported sales');

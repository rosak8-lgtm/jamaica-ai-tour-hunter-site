// JAMAICA city-only IP hint. Deploy as a separate Cloudflare Worker.
// No external requests, no storage, no IP/coordinates returned.
const SITE="https://rosak8-lgtm.github.io";
const names=[
["Иркутск","Irkutsk"],["Москва","Moscow","Moskva"],["Санкт-Петербург","Saint Petersburg","St Petersburg","Sankt Peterburg"],
["Новосибирск","Novosibirsk"],["Красноярск","Krasnoyarsk"],["Екатеринбург","Yekaterinburg","Ekaterinburg"],
["Владивосток","Vladivostok"],["Хабаровск","Khabarovsk"],["Казань","Kazan"],["Сочи","Sochi"],
["Минеральные Воды","Mineralnye Vody","Mineralnyye Vody"],["Самара","Samara"],["Архангельск","Arkhangelsk"],
["Астрахань","Astrakhan"],["Барнаул","Barnaul"],["Волгоград","Volgograd"],["Горно-Алтайск","Gorno Altaysk","Gorno Altaisk"],
["Калининград","Kaliningrad"],["Кемерово","Kemerovo"],["Краснодар","Krasnodar"],["Магнитогорск","Magnitogorsk"],
["Мурманск","Murmansk"],["Нижнекамск","Nizhnekamsk"],["Нижний Новгород","Nizhny Novgorod","Nizhniy Novgorod"],
["Новокузнецк","Novokuznetsk"],["Омск","Omsk"],["Оренбург","Orenburg"],["Саратов","Saratov"],["Сургут","Surgut"],
["Сыктывкар","Syktyvkar"],["Томск","Tomsk"],["Тюмень","Tyumen"],["Ульяновск","Ulyanovsk"],["Уфа","Ufa"],
["Челябинск","Chelyabinsk"],["Махачкала","Makhachkala"],["Нижневартовск","Nizhnevartovsk"],["Пермь","Perm"],
["Ставрополь","Stavropol"],["Ханты-Мансийск","Khanty Mansiysk","Khanty Mansiisk"],["Абакан","Abakan"],
["Пенза","Penza"],["Ижевск","Izhevsk"],["Геленджик","Gelendzhik"],["Магадан","Magadan"],["Орск","Orsk"],
["Грозный","Grozny"],["Кировск","Kirovsk"],["Петропавловск - Камчатский","Petropavlovsk Kamchatsky","Petropavlovsk Kamchatskiy"],
["Южно-Сахалинск","Yuzhno Sakhalinsk"],["Улан-удэ","Ulan Ude"],["Саранск","Saransk"],["Чебоксары","Cheboksary"],
["Якутск","Yakutsk"],["Анадырь","Anadyr"],["Благовещенск","Blagoveshchensk"],["Владикавказ","Vladikavkaz"],
["Киров","Kirov"],["Нальчик","Nalchik"],["Элиста","Elista"]
];
function norm(x){return typeof x==="string"?x.normalize("NFKC").toLowerCase().replace(/[ё]/g,"е").replace(/[^\p{L}\p{N}]+/gu," ").trim():"";}
const aliases=new Map(names.flatMap(([city,...other])=>[city,...other].map(x=>[norm(x),city])));
export function cityHint(cf){
 if(!cf||cf.country!=="RU"||typeof cf.city!=="string"||cf.city.length>120)return null;
 const city=aliases.get(norm(cf.city))||null;
 // These names have common homonyms in Russia. Require known region for them.
 if(city==="Кировск" && !/murmansk|мурманск/i.test(cf.region||""))return null;
 if(city==="Киров" && !/kirov|киров/i.test(cf.region||""))return null;
 if(city==="Благовещенск" && !/amur|амур/i.test(cf.region||""))return null;
 return city;
}
export default {async fetch(request){
 const url=new URL(request.url);
 const origin=request.headers.get("Origin");
 const headers={"Content-Type":"application/json; charset=utf-8","Cache-Control":"private, no-store","Vary":"Origin","X-Content-Type-Options":"nosniff"};
 if(origin===SITE)headers["Access-Control-Allow-Origin"]=SITE;
 if(origin&&origin!==SITE)return new Response(null,{status:403,headers});
 if(url.pathname!=="/api/departure-city"||url.search)return new Response(null,{status:404,headers});
 if(request.method!=="GET")return new Response(null,{status:405,headers:{...headers,Allow:"GET"}});
 return new Response(JSON.stringify({schema:"jamaica.departure-hint.v1",city:cityHint(request.cf),source:"IP_APPROXIMATE"}),{headers});
}};

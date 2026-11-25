/* Search diagnostics over ALREADY eligible rows; never bypass proof policy. */
(function(root){
"use strict";
function analyze(rows,q,extra=()=>true){
 const norm=x=>String(x||"").trim().toLocaleLowerCase("ru");
 const city=rows.filter(x=>norm(x.origin)===norm(q.origin));
 const country=city.filter(x=>!q.country||norm(x.country)===norm(q.country));
 const dateOK=x=>(!q.from||x.depart_date>=q.from)&&(!q.to||x.depart_date<=q.to);
 const nightOK=x=>!q.nights.length||q.nights.includes(x.nights);
 const dates=country.filter(dateOK), nights=dates.filter(nightOK);
 const extraRows=country.filter(extra);
 const alternatives=[
  {key:"nights",count:extraRows.filter(dateOK).length,enabled:q.nights.length>0},
  {key:"dates",count:extraRows.filter(nightOK).length,enabled:!!(q.from||q.to)},
  {key:"both",count:extraRows.length,enabled:!!(q.from||q.to)&&q.nights.length>0},
  {key:"countries",count:city.filter(x=>norm(x.country)!==norm(q.country)&&dateOK(x)&&nightOK(x)&&extra(x)).length,enabled:!!q.country}
 ].filter(x=>x.enabled&&x.count>0);
 return {city:city.length,country:country.length,dates:dates.length,nights:nights.length,
  durations:[...new Set(dates.map(x=>x.nights))].sort((a,b)=>a-b),
  alternatives};
}
root.JamaicaSearchRecovery=Object.freeze({analyze});
})(globalThis);

/* Room groups, ages at departure and lossless customer selection. No quote math. */
(function(root){
 "use strict";
 root.JamaicaTravelerUI=Object.freeze({create:function(){
  const T=root.JamaicaTravelers;
  const el=id=>document.getElementById(id);
  let active=[{adults:2,child_ages:[]}];
  let roomSequence=1;
  function add(tag,text,cls,parent){
   const x=document.createElement(tag);if(cls)x.className=cls;
   if(text!==undefined)x.textContent=text;
   if(parent)parent.append(x);
   return x;
  }
  function drawAges(box,kids,seed=[]){
   const old=[...box.querySelectorAll("select")].map(x=>x.value);
   box.replaceChildren();
   for(let i=0;i<kids;i++){
    const row=add("div",undefined,"childAgeField",box);
    const label=add("label","Ребёнок "+(i+1)+" — лет на дату вылета",undefined,row);
    const select=add("select",undefined,"childAgeSelect",row);
    select.id=box.id+"-age-"+i;label.htmlFor=select.id;select.required=true;
    const unknown=add("option","Выберите возраст",undefined,select);unknown.value="";
    for(let age=0;age<=T.MAX_CHILD_AGE;age++){
     const opt=add("option",age+" лет",undefined,select);opt.value=String(age);
    }
    const value=seed[i]!==undefined?String(seed[i]):old[i]||"";
    if(value!=="")select.value=value;
    select.addEventListener("change",display);
   }
  }
  function renumber(){
   [...el("extraRooms").children].forEach((room,i)=>{
    room.querySelector(".partyRoomHeader strong").textContent="Номер "+(i+2);
   });
   el("addRoom").disabled=el("extraRooms").children.length>=T.MAX_ROOMS-1;
  }
  function addRoom(initial={adults:1,child_ages:[]}){
   if(el("extraRooms").children.length>=T.MAX_ROOMS-1)return;
   const no=++roomSequence;
   const box=add("div",undefined,"partyRoom");
   const header=add("div",undefined,"partyRoomHeader",box);
   add("strong","Номер "+no,undefined,header);
   const remove=add("button","Удалить номер","removeRoom",header);
   remove.type="button";remove.addEventListener("click",()=>{
    box.remove();renumber();display();
   });
   const fields=add("div",undefined,"partyRoomFields",box);
   const aField=add("div",undefined,"childAgeField",fields);
   const aLabel=add("label","Взрослых",undefined,aField);
   const adults=add("input",undefined,"roomAdults",aField);
   adults.type="number";adults.min=1;adults.max=12;adults.required=true;
   adults.id="room-adults-"+no;adults.value=String(initial.adults);aLabel.htmlFor=adults.id;
   const cField=add("div",undefined,"childAgeField",fields);
   const cLabel=add("label","Детей",undefined,cField);
   const kids=add("input",undefined,"roomKids",cField);
   kids.type="number";kids.min=0;kids.max=10;kids.required=true;
   kids.id="room-kids-"+no;kids.value=String(initial.child_ages.length);
   cLabel.htmlFor=kids.id;
   const ageBox=add("div",undefined,"partyAges",box);ageBox.id="room-age-fields-"+no;
   drawAges(ageBox,initial.child_ages.length,initial.child_ages);
   adults.addEventListener("input",display);
   kids.addEventListener("input",()=>{
    drawAges(ageBox,Math.min(10,Math.max(0,Number(kids.value)||0)));
    display();
   });
   el("extraRooms").append(box);renumber();display();
  }
  function group(adults,kids,box){
   const count=Number(kids.value),selects=[...box.querySelectorAll("select")];
   if(!Number.isInteger(count)||count!==selects.length||
     selects.some(s=>s.value===""))return null;
   return {adults:Number(adults.value),child_ages:selects.map(s=>Number(s.value))};
  }
  function read(){
   const first=group(el("adults"),el("kids"),el("primaryChildAges"));
   if(!first)return null;
   const result=[first];
   for(const row of el("extraRooms").children){
    const g=group(row.querySelector(".roomAdults"),row.querySelector(".roomKids"),
      row.querySelector(".partyAges"));
    if(!g)return null;
    result.push(g);
   }
   return T.normalize(result);
  }
  function display(){
   const g=read();
   el("partySummary").textContent=g?T.label(g):
     "Укажите возраст детей и проверьте состав номеров.";
   el("partyError").hidden=true;
  }
  function apply(group){
   const rooms=T.normalize(group);if(!rooms)return false;
   el("adults").value=String(rooms[0].adults);
   el("kids").value=String(rooms[0].child_ages.length);
   drawAges(el("primaryChildAges"),rooms[0].child_ages.length,rooms[0].child_ages);
   el("extraRooms").replaceChildren();
   rooms.slice(1).forEach(addRoom);
   active=rooms;renumber();display();
   return true;
  }
  function commit(){
   const rooms=read();
   if(!rooms){
    el("partyError").textContent="Укажите возраст каждого ребёнка на дату вылета. Максимум 5 номеров, 12 взрослых и 10 детей.";
    el("partyError").hidden=false;
    el("partyError").scrollIntoView({behavior:"smooth",block:"center"});
    return null;
   }
   active=rooms;display();return rooms;
  }
  el("adults").addEventListener("input",display);
  el("kids").addEventListener("input",()=>{
   drawAges(el("primaryChildAges"),Math.min(10,Math.max(0,Number(el("kids").value)||0)));
   display();
  });
  el("addRoom").addEventListener("click",()=>addRoom());
  drawAges(el("primaryChildAges"),0);renumber();
  const params=new URLSearchParams(root.location.search);
  if(params.has("rooms")){
   const saved=T.fromQuery(params);if(saved)apply(saved);
  }
  display();
  return Object.freeze({current:()=>T.normalize(active),read,commit,apply});
 }});
})(typeof window!=="undefined"?window:globalThis);

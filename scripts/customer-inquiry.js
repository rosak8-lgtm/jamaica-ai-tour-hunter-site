(function(root){
"use strict";
function url(s){
 try{const u=new URL(s);return u.protocol==="https:"&&!u.username&&!u.password&&!u.hash&&!u.search?u:null;}catch{return null;}
}
function ready(c){
 if(!c||c.schema!=="jamaica.inquiry-config.v1"||c.enabled!==true||c.privacy_approved!==true||
 typeof c.controller_name!=="string"||c.controller_name.trim().length<3||c.controller_name.length>200||
 typeof c.policy_version!=="string"||!/^[A-Za-z0-9._-]{1,64}$/.test(c.policy_version))return false;
 const e=url(c.endpoint),p=url(c.privacy_url);
 return !!e&&!!p&&e.pathname==="/v1/customer-inquiries";
}
function body(id,rooms,kind,value,consent,c,requestId){
 if(!ready(c)||consent!==true||!(/^(?:p|pg)_[a-f0-9]{24}$/).test(id)||!(/^[a-f0-9]{32}$/).test(requestId))throw Error("INVALID_REQUEST");
 const party=root.JamaicaTravelers.normalize(rooms);
 if(!party||typeof value!=="string")throw Error("INVALID_REQUEST");
 value=value.trim();
 if(kind==="phone")value=value.replace(/[ ()-]/g,"");
 if(!(kind==="phone"&&/^\+[1-9][0-9]{7,14}$/.test(value))&&
    !(kind==="email"&&value.length<=254&&/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)))throw Error("INVALID_CONTACT");
 return {request_id:requestId,preview_id:id,rooms:party,contact:{kind,value},consent:true,policy_version:c.policy_version};
}
function receipt(r){
 return !!r&&r.status==="INQUIRY_RECEIVED"&&/^j_[a-f0-9]{32}$/.test(r.ticket||"")&&r.booked===false&&r.payment_required===false;
}
function node(tag,label,parent){const e=document.createElement(tag);e.textContent=label||"";parent.append(e);return e;}
async function mount(container,{getSelection,rooms,isCurrent}){
 if(!container||container.dataset.inquiryMounted)return;
 container.dataset.inquiryMounted="yes";
 let c;
 try{const r=await fetch("./inquiry-config.json",{cache:"no-store",signal:AbortSignal.timeout(5000)});if(!r.ok)return;c=await r.json();}catch{return;}
 if(!ready(c))return;
 const form=node("form","",container);
 const heading=node("h2","Запросить точную стоимость",form);
 node("p","Оставьте телефон или email для связи. Это заявка на расчёт, не договор, бронь или оплата.",form);
 const kindLabel=node("label","Способ связи ",form);
 const kind=node("select","",kindLabel);
 for(const [value,label] of [["phone","Телефон"],["email","Электронная почта"]]){const o=node("option",label,kind);o.value=value;}
 const contactLabel=node("label","Контакт ",form);
 const contact=node("input","",contactLabel);
 contact.type="tel";contact.autocomplete="tel";contact.maxLength=254;contact.required=true;
 kind.addEventListener("change",()=>{contact.value="";contact.type=kind.value==="phone"?"tel":"email";contact.autocomplete=kind.value==="phone"?"tel":"email";});
 const consentLabel=node("label","",form),consent=node("input","",consentLabel);
 consent.type="checkbox";consent.required=true;
 node("span"," Согласен на обработку контакта для расчёта тура: "+c.controller_name+". ",consentLabel);
 const policy=node("a","Политика обработки данных",consentLabel);policy.href=c.privacy_url;policy.target="_blank";policy.rel="noopener noreferrer";
 const submit=node("button","Отправить заявку на расчёт",form);submit.type="submit";submit.className="btn";
 const status=node("p","",form);status.setAttribute("role","status");status.setAttribute("aria-live","polite");
 let pending=null,busy=false,done=false;
 const update=()=>{const row=getSelection();container.hidden=!row||!isCurrent(row);submit.disabled=busy||done||container.hidden;};
 update();
 setInterval(update,1000);
 form.addEventListener("submit",async event=>{
  event.preventDefault();if(busy||done)return;
  const row=getSelection();if(!row||!isCurrent(row)){update();return;}
  let payload;
  try{
   const key=Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,"0")).join("");
   payload=body(row.id,rooms,kind.value,contact.value,consent.checked,c,key);
   if(pending&&JSON.stringify({...pending,request_id:""})===JSON.stringify({...payload,request_id:""}))payload=pending;
  }catch{status.textContent="Проверьте контакт и согласие.";return;}
  pending=payload;busy=true;update();status.textContent="Отправляем запрос…";
  try{
   const response=await fetch(c.endpoint,{method:"POST",credentials:"omit",cache:"no-store",redirect:"error",signal:AbortSignal.timeout(10000),headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
   if(response.status===409){status.textContent="Вариант изменился или запрос конфликтует. Обновите поиск.";pending=null;return;}
   if(response.status===429){status.textContent="Слишком много запросов. Повторите позднее.";return;}
   if(response.status!==202||!receipt(await response.json()))throw Error("UNCONFIRMED");
   done=true;pending=null;contact.value="";consent.checked=false;
   status.textContent="Заявка принята. Номер обращения сохранён сервером. Это не бронь и не оплата.";
  }catch{status.textContent="Получение заявки не подтверждено. Повторите отправку с тем же контактом.";}
  finally{busy=false;update();}
 });
}
root.JamaicaCustomerInquiry=Object.freeze({ready,body,receipt,mount});
})(globalThis);

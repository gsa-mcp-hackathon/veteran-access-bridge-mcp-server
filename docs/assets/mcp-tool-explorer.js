/* Progressive enhancement only: the full catalog is already in the HTML. */
(function(){
function init(){
const root=document.getElementById("vab-tool-explorer");
if(!root||root.dataset.enhanced==="true")return;
const rows=Array.from(root.querySelectorAll(".vab-tool-row"));
const search=root.querySelector("#vab-tool-search"),category=root.querySelector("#vab-tool-category"),attachment=root.querySelector("#vab-tool-attachment"),count=root.querySelector("#vab-tool-count"),more=root.querySelector("#vab-tool-more"),empty=root.querySelector("#vab-tool-empty"),controls=root.querySelector(".vab-tool-controls");
if(!rows.length||!search||!category||!attachment||!more||!count||!controls)return;
root.dataset.enhanced="true";controls.hidden=false;
let expanded=false;
function render(){
const q=search.value.trim().toLowerCase();
const matched=rows.filter(r=>(!q||r.dataset.search.toLowerCase().includes(q))&&(category.value==="all"||r.dataset.category===category.value)&&(attachment.value==="all"||r.dataset.attached===(attachment.value==="attached"?"yes":"no")));
const filtered=Boolean(q)||category.value!=="all"||attachment.value!=="all";
const visible=(!filtered&&!expanded)?matched.slice(0,10):matched;const show=new Set(visible);
for(const row of rows){row.hidden=!show.has(row);if(row.hidden)row.open=false;}
count.textContent=visible.length+" of "+rows.length+" tools shown";
empty.hidden=matched.length!==0;more.hidden=filtered||rows.length<=10;
more.textContent=expanded?"Show fewer tools":"Show all "+rows.length+" tools";
more.setAttribute("aria-expanded",String(expanded));
}
search.addEventListener("input",render);category.addEventListener("change",render);attachment.addEventListener("change",render);
more.addEventListener("click",()=>{expanded=!expanded;render();});render();
}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();
if(window.document$&&typeof window.document$.subscribe==="function")window.document$.subscribe(init);
})();
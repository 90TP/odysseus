"""Review page: approve Aerith's fixes and pick features to build.

Served at /api/companion/aerith/maintenance/page so the Android WebView and
the desktop browser get the same screen.  All data is rendered with
textContent, never innerHTML, because incidents carry raw log text.
"""

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aerith updates</title>
<style>
  :root{--win1:#0b2a8a;--win2:#020b45;--edge:#c8d0e8;--text:#f2f4ff;--dim:#a9b3d9;--ok:#7fe08a;--bad:#ff8a80;--warn:#ffd166}
  *{box-sizing:border-box}
  body{margin:0;padding:16px;background:#05060f;color:var(--text);font:15px/1.45 system-ui,-apple-system,sans-serif}
  h1{font-size:20px;margin:0 0 12px;letter-spacing:.04em}
  .win{background:linear-gradient(180deg,var(--win1),var(--win2));border:2px solid var(--edge);border-radius:8px;
       box-shadow:0 0 0 2px #2b3566 inset;padding:14px 16px;margin:0 0 16px;max-width:900px}
  .win h2{font-size:14px;text-transform:uppercase;letter-spacing:.12em;color:var(--dim);margin:0 0 10px}
  .item{border-top:1px solid #ffffff22;padding:10px 0}
  .item:first-of-type{border-top:0}
  .title{font-weight:600}
  .meta{color:var(--dim);font-size:13px}
  .tag{display:inline-block;border:1px solid var(--dim);border-radius:10px;padding:0 7px;font-size:12px;margin-right:4px}
  .ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}
  button{font:inherit;font-size:13px;margin:8px 8px 0 0;padding:6px 12px;border-radius:6px;cursor:pointer;
         border:1px solid var(--edge);background:#1b2f8f;color:var(--text)}
  button.primary{background:#e8ecff;color:#0b1a5c;font-weight:600}
  pre{white-space:pre-wrap;word-break:break-word;background:#00000055;padding:8px;border-radius:6px;
      font-size:12px;max-height:360px;overflow:auto}
  .empty{color:var(--dim);font-style:italic}
  #msg{min-height:1.4em;margin-bottom:10px}
  .chat{max-height:420px;overflow:auto;margin-bottom:8px}
  .bubble{padding:8px 10px;border-radius:8px;margin:6px 0;white-space:pre-wrap;max-width:92%}
  .bubble.cid{background:#00000040;border:1px solid #ffffff25}
  .bubble.user{background:#e8ecff;color:#0b1a5c;margin-left:auto}
  .who{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--dim);margin-bottom:2px}
  .bubble.user .who{color:#3b4a8a}
  .changes{font-size:12px;color:var(--ok);margin-top:4px}
  .send{display:flex;gap:8px}
  .send textarea{flex:1;font:inherit;padding:8px;border-radius:6px;border:1px solid var(--edge);
                 background:#00000055;color:var(--text);min-height:44px;resize:vertical}
  .send button{margin:0;align-self:flex-end}
  .badge{background:var(--warn);color:#1b1300;border-radius:9px;padding:0 7px;font-size:12px;margin-left:6px}
</style></head>
<body>
<h1>Aerith &middot; Updates</h1>
<div id="msg" class="meta"></div>
<div class="win"><h2>Ready for your review</h2><div id="ready"></div></div>
<div class="win"><h2>Planning with Cid<span id="cidBadge"></span></h2>
  <div id="cidChat" class="chat"></div>
  <form id="cidForm" class="send"><textarea id="cidInput" placeholder="Talk it through with Cid. e.g. “Do 1 and 3, skip 2”"></textarea>
  <button class="primary" type="submit">Send</button></form></div>
<div class="win"><h2>Options on the table</h2><div id="ideas"></div></div>
<div class="win"><h2>Aerith is working on</h2><div id="working"></div></div>
<div class="win"><h2>Errors Aerith has seen</h2><div id="errors"></div></div>
<script nonce="__NONCE__">
const API = "/api/companion/aerith/maintenance";
const $ = (id) => document.getElementById(id);
function el(tag, cls, text){const e=document.createElement(tag); if(cls) e.className=cls; if(text!=null) e.textContent=text; return e;}
function when(t){return t ? new Date(t*1000).toLocaleString() : "";}
function say(text, cls){const m=$("msg"); m.textContent=text; m.className="meta "+(cls||"");}
async function call(path, opts){
  const r = await fetch(API+path, Object.assign({credentials:"same-origin", headers:{"Content-Type":"application/json"}}, opts||{}));
  let body = {}; try { body = await r.json(); } catch(e) {}
  if(!r.ok) throw new Error(body.detail || ("HTTP "+r.status));
  return body;
}
function button(label, cls, fn){const b=el("button", cls, label); b.onclick=async()=>{b.disabled=true; try{await fn();}catch(e){say(e.message,"bad");} b.disabled=false; load();}; return b;}
function tags(p){const d=el("div","meta"); (p.platforms||[]).forEach(x=>d.appendChild(el("span","tag",x))); if(p.effort) d.appendChild(el("span","tag",p.effort+" effort")); return d;}
function empty(box, text){box.replaceChildren(el("div","empty",text));}

function renderReady(list){
  const box=$("ready"); if(!list.length) return empty(box,"Nothing waiting for you.");
  box.replaceChildren(...list.map(p=>{
    const it=el("div","item");
    it.append(el("div","title",p.title), tags(p), el("div","meta",p.kind+" · branch "+p.branch+" · tests passed"));
    if(p.report) it.appendChild(el("p",null,p.report));
    if(p.diff_stat) it.appendChild(el("pre",null,p.diff_stat));
    const diff=el("pre"); diff.hidden=true; it.appendChild(diff);
    it.append(
      button("Approve & merge","primary", async()=>{const r=await call("/proposals/"+p.id+"/approve",{method:"POST"}); say(r.message,"ok");}),
      button("Show full diff",null, async()=>{const r=await call("/proposals/"+p.id); diff.textContent=r.diff||"(empty)"; diff.hidden=false;}),
      button("Reject",null, async()=>{await call("/proposals/"+p.id+"/reject",{method:"POST",body:"{}"}); say("Rejected.");}));
    return it;}));
}
function renderIdeas(list){
  const box=$("ideas"); if(!list.length) return empty(box,"No suggestions yet. They appear after research finishes.");
  box.replaceChildren(...list.map(p=>{
    const it=el("div","item");
    it.append(el("div","title",p.title), tags(p), el("p",null,p.summary));
    if(p.rationale) it.appendChild(el("div","meta","Why: "+p.rationale));
    if(p.research_query) it.appendChild(el("div","meta","From research: "+p.research_query));
    it.append(
      button("Build this","primary", async()=>{await call("/proposals/"+p.id+"/choose",{method:"POST"}); say("Aerith is building “"+p.title+"”.","ok");}),
      button("Not now",null, async()=>{await call("/proposals/"+p.id+"/reject",{method:"POST",body:"{}"});}));
    return it;}));
}
function renderWorking(list){
  const box=$("working"); if(!list.length) return empty(box,"Idle.");
  box.replaceChildren(...list.map(p=>{
    const it=el("div","item");
    const n = p.attempt||1;
    let state = p.status==="failed" ? "Gave up for now: "+(p.error||"") : p.status;
    if(p.status!=="failed" && n>1) state += " · attempt "+n+": investigating why the usual fix didn’t work";
    if(p.status!=="failed" && p.agreed_with) state += " · agreed with Cid";
    it.append(el("div","title",p.title), tags(p), el("div","meta "+(p.status==="failed"?"bad":"warn"),state));
    if(p.status==="failed" && n>1) it.appendChild(el("div","meta","Tried "+n+" different approaches."));
    if(p.test_output && p.status==="failed") it.appendChild(el("pre",null,p.test_output));
    if(p.status==="failed"){
      it.appendChild(button("Try another way","primary", async()=>{
        if(p.kind==="feature") await call("/proposals/"+p.id+"/choose",{method:"POST"});
        else await call("/incidents/"+p.incident_id+"/fix",{method:"POST"});
        say("Aerith is digging into why it failed.","ok");}));
      it.appendChild(button("Discard",null, async()=>{await call("/proposals/"+p.id+"/reject",{method:"POST",body:"{}"});}));
    }
    return it;}));
}
let lastCid = "";
function renderCid(conv){
  const box=$("cidChat");
  $("cidBadge").replaceChildren(...(conv.unread ? [el("span","badge",conv.unread+" new")] : []));
  const sig = conv.messages.map(m=>m.id).join(",");
  if(sig===lastCid) return; lastCid = sig;
  if(!conv.messages.length){ empty(box,"Cid will message you when research turns up something worth building."); return; }
  box.replaceChildren(...conv.messages.map(m=>{
    const b=el("div","bubble "+(m.role==="cid"?"cid":"user"));
    b.append(el("div","who",m.role==="cid"?"Cid":"You"), document.createTextNode(m.content));
    const c=m.changes||{}; const bits=[];
    if((c.agreed||[]).length) bits.push("Agreed: "+c.agreed.length+" sent to Aerith to build");
    if((c.added||[]).length) bits.push("Added "+c.added.length);
    if((c.revised||[]).length) bits.push("Reworded "+c.revised.length);
    if((c.dropped||[]).length) bits.push("Dropped "+c.dropped.length);
    if(bits.length) b.appendChild(el("div","changes",bits.join(" · ")));
    return b;}));
  box.scrollTop = box.scrollHeight;
  if(conv.unread) call("/cid/read",{method:"POST"}).catch(()=>{});
}
$("cidForm").onsubmit = async (ev)=>{
  ev.preventDefault();
  const input=$("cidInput"), text=input.value.trim(); if(!text) return;
  const btn=ev.target.querySelector("button"); btn.disabled=true; input.disabled=true;
  try{ await call("/cid",{method:"POST",body:JSON.stringify({message:text})}); input.value=""; }
  catch(e){ say(e.message,"bad"); }
  btn.disabled=false; input.disabled=false; load();
};
function renderErrors(list){
  const box=$("errors"); if(!list.length) return empty(box,"No errors seen. Lovely.");
  box.replaceChildren(...list.slice(0,30).map(i=>{
    const it=el("div","item");
    it.append(el("div","title",i.message.split("\\n")[0].slice(0,200)),
      el("div","meta",i.platform+" · "+i.source+" · ×"+i.count+" · last "+when(i.last_seen)+" · "+i.status));
    if(i.detail){const d=el("pre",null,i.detail); d.hidden=true; it.appendChild(d);
      it.appendChild(button("Trace",null, async()=>{d.hidden=!d.hidden;}));}
    if(["open","fix_failed","dismissed"].includes(i.status))
      it.appendChild(button("Ask Aerith to fix","primary", async()=>{await call("/incidents/"+i.id+"/fix",{method:"POST"}); say("Aerith is on it.","ok");}));
    if(i.status==="open") it.appendChild(button("Ignore",null, async()=>{await call("/incidents/"+i.id+"/dismiss",{method:"POST"});}));
    return it;}));
}
async function load(){
  try{
    const s = await call("/status");
    if(!s.enabled){ say("Aerith maintenance is off. Set AERITH_MAINTENANCE_ENABLED=1 and restart.","warn"); return; }
    if(!s.owner_configured) say("Set AERITH_MAINTENANCE_OWNER so Aerith knows which account to work as.","warn");
    const [{proposals}, {incidents}, conv] = await Promise.all([call("/proposals"), call("/incidents"), call("/cid")]);
    renderCid(conv);
    renderReady(proposals.filter(p=>p.status==="ready"));
    renderIdeas(proposals.filter(p=>p.kind==="feature" && p.status==="offered"));
    renderWorking(proposals.filter(p=>["queued","building","failed"].includes(p.status)));
    renderErrors(incidents.filter(i=>i.status!=="resolved"));
  }catch(e){ say(e.message,"bad"); }
}
load(); setInterval(load, 15000);
</script>
</body></html>"""


def render_page(nonce: str) -> str:
    return PAGE.replace("__NONCE__", nonce or "")

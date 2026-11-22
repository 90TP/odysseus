"""FF7 menu-style character sheet. Everything is drawn with textContent."""

import json

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Character status</title>
<style>
  :root{--w1:#1238a8;--w2:#030d52;--edge:#d4dbef;--text:#f4f6ff;--dim:#9aa6d6;--sp1:#4fd4c4;--sp2:#2b7fd6;
        --mp1:#e6f06a;--mp2:#4fa84a;--lim1:#ff8ab4;--lim2:#c2185b;--ok:#7fe08a;--warn:#ffd166;--bad:#ff8a80}
  *{box-sizing:border-box}
  body{margin:0;padding:16px;background:#04050c;color:var(--text);font:15px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif}
  .wrap{max-width:860px;margin:0 auto;display:grid;gap:14px}
  .win{background:linear-gradient(180deg,var(--w1),var(--w2));border:2px solid var(--edge);border-radius:7px;
       box-shadow:0 0 0 2px #26306a inset,0 4px 18px #0008;padding:14px 16px}
  .win h2{margin:0 0 10px;font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--dim)}
  .hero{display:grid;grid-template-columns:128px 1fr;gap:16px;align-items:center}
  .avatar{width:128px;height:128px;border:2px solid var(--edge);border-radius:4px;background:#0a1a5c;
          display:flex;align-items:center;justify-content:center;font-size:56px;font-weight:700;color:var(--dim);overflow:hidden}
  .avatar img{width:100%;height:100%;object-fit:cover}
  .name{font-size:24px;font-weight:700;letter-spacing:.04em}
  .lv{color:var(--dim);font-weight:600;margin:2px 0 8px}.lv b{color:var(--text);font-size:18px;margin-left:6px}
  .stat{display:grid;grid-template-columns:40px 1fr;gap:8px;align-items:center;margin:6px 0}
  .stat .k{font-weight:700;color:var(--dim);font-size:13px}
  .num{font-variant-numeric:tabular-nums;font-weight:600;font-size:14px}
  .num small{color:var(--dim);font-weight:400}
  .bar{height:6px;border-radius:3px;background:#00000080;overflow:hidden;margin-top:3px;max-width:240px}
  .bar i{display:block;height:100%;width:0;transition:width .6s}
  .sp i{background:linear-gradient(90deg,var(--sp2),var(--sp1))}
  .mp i{background:linear-gradient(90deg,var(--mp2),var(--mp1))}
  .lim i{background:linear-gradient(90deg,var(--lim2),var(--lim1))}
  .lim.full i{animation:flash .8s infinite alternate}
  @keyframes flash{from{filter:brightness(1)}to{filter:brightness(1.8)}}
  .exp{color:var(--dim);font-size:13px;margin-top:8px}.exp b{color:var(--text)}
  .row{display:grid;grid-template-columns:52px 1fr auto;gap:10px;padding:7px 0;border-top:1px solid #ffffff1c;align-items:center}
  .row:first-of-type{border-top:0}
  .slot{color:var(--warn);font-weight:700;font-size:13px}
  .dev small{display:block;color:var(--dim);font-size:12px}
  .batt{font-variant-numeric:tabular-nums;font-weight:600}
  .batt.low{color:var(--bad)}.batt.chg{color:var(--ok)}
  .empty{color:var(--dim);font-style:italic}
  .materia{display:flex;flex-wrap:wrap;gap:10px 16px}
  .orb{display:flex;align-items:center;gap:7px;font-size:13px}
  .orb i{width:16px;height:16px;border-radius:50%;flex:none;box-shadow:0 0 6px currentColor;
         background:radial-gradient(circle at 35% 30%,#fff 0 12%,currentColor 45%,#000a 100%)}
  .status{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:6px 18px}
  .status div{display:flex;justify-content:space-between;gap:8px;border-bottom:1px dotted #ffffff22;padding:4px 0}
  .status span{color:var(--dim)}
  .status b{font-variant-numeric:tabular-nums;text-align:right}
  .status b small{display:block;font-weight:400;color:var(--dim);font-size:11px}
  .foot{color:var(--dim);font-size:12px;text-align:right}
  .foot.stale{color:var(--warn)}
  @media (max-width:520px){.hero{grid-template-columns:88px 1fr}.avatar{width:88px;height:88px;font-size:40px}}
</style></head>
<body><div class="wrap">
  <div class="win"><div class="hero">
    <div class="avatar" id="avatar"></div>
    <div>
      <div class="name" id="name"></div>
      <div class="lv">LV<b id="lv">--</b></div>
      <div class="stat"><span class="k">SP</span><div><div class="num" id="sp">--</div><div class="bar sp"><i id="spBar"></i></div></div></div>
      <div class="stat"><span class="k">MP</span><div><div class="num" id="mp">--</div><div class="bar mp"><i id="mpBar"></i></div></div></div>
      <div class="stat"><span class="k">Limit</span><div><div class="num" id="lim">--</div><div class="bar lim" id="limWrap"><i id="limBar"></i></div></div></div>
      <div class="exp" id="exp"></div>
    </div>
  </div></div>
  <div class="win"><h2>Equip</h2><div id="equip"></div></div>
  <div class="win"><h2>Materia</h2><div class="materia" id="materia"></div></div>
  <div class="win"><h2>Status</h2><div class="status" id="status"></div></div>
  <div class="foot" id="foot"></div>
</div>
<script nonce="__NONCE__">
const CHAR = __CHAR__;
const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
function ago(t){ if(!t) return ""; const m = Math.round((Date.now()/1000 - t)/60);
  return m < 1 ? "just now" : m < 60 ? m+"m ago" : m < 1440 ? Math.round(m/60)+"h ago" : Math.round(m/1440)+"d ago"; }
function fmtMins(m){ m = Math.round(m); return Math.floor(m/60)+"h "+String(m%60).padStart(2,"0")+"m"; }
function setGauge(id, g, text){
  $(id).replaceChildren();
  if(!g){ $(id).textContent = "--"; $(id+"Bar").style.width = "0"; return; }
  $(id).append(text(g)); $(id+"Bar").style.width = (g.fraction*100).toFixed(1)+"%";
}
function render(s){
  document.title = s.name + " · Status";
  $("name").textContent = s.name;
  const av = $("avatar"); av.replaceChildren();
  if (s.avatar_url){ const img = el("img"); img.alt = s.name; img.src = s.avatar_url; av.appendChild(img); }
  else av.textContent = (s.name || "?").slice(0,1).toUpperCase();
  $("lv").textContent = s.level ?? "--";
  setGauge("sp", s.sp, g => { const f = document.createDocumentFragment();
    f.append(String(g.current)+"/"+g.max+" "); f.append(el("small", null, "mins · "+fmtMins(g.current)+" slept")); return f; });
  setGauge("mp", s.mp, g => String(g.current)+"/"+g.max);
  setGauge("lim", s.limit, g => g.full ? "LIMIT BREAK" : g.current+"% stress");
  $("limWrap").classList.toggle("full", !!(s.limit && s.limit.full));
  $("exp").replaceChildren();
  if (s.exp != null){ $("exp").append("EXP ", el("b", null, s.exp+" days"), "   ·   To next level ", el("b", null, s.next_level+" days")); }

  const eq = $("equip"); eq.replaceChildren();
  s.equipment.forEach(slot => {
    const r = el("div","row"); r.append(el("span","slot",slot.label));
    const d = slot.device;
    if (!d){ r.append(el("span","empty","Nothing equipped"), el("span")); eq.appendChild(r); return; }
    const dev = el("div","dev", [d.make, d.model].filter(Boolean).join(" ") || d.id);
    dev.appendChild(el("small", null, d.kind+" · "+ago(d.updated_at)));
    let b = el("span","batt","");
    if (d.battery != null){ b.textContent = Math.round(d.battery)+"%"+(d.charging?" charging":"");
      b.classList.toggle("low", d.battery <= 20 && !d.charging); b.classList.toggle("chg", !!d.charging); }
    r.append(dev, b); eq.appendChild(r);
  });

  const mat = $("materia"); mat.replaceChildren();
  if (!s.materia.length) mat.appendChild(el("span","empty","No materia equipped"));
  s.materia.forEach(a => { const o = el("span","orb"); const i = el("i"); i.style.color = a.colour;
    o.title = [a.category, a.device].filter(Boolean).join(" · "); o.append(i, a.name); mat.appendChild(o); });

  const st = $("status"); st.replaceChildren();
  const rows = [];
  if (s.location) rows.push({label:"Location", value:s.location.label, unit:"", source:"", updated_at:s.location.updated_at});
  rows.push(...s.status);
  if (!rows.length) st.appendChild(el("span","empty","No readings yet"));
  rows.forEach(r => {
    let v = r.key === "sleep_minutes" ? fmtMins(r.value) : String(r.value) + (r.unit ? " "+r.unit : "");
    const d = el("div"); const b = el("b", null, v);
    b.appendChild(el("small", null, [r.source, ago(r.updated_at)].filter(Boolean).join(" · ")));
    d.append(el("span", null, r.label), b); st.appendChild(d);
  });
  $("foot").textContent = s.updated_at ? (s.stale ? "Readings are old · " : "Updated ") + ago(s.updated_at) : "Waiting for your devices to report in.";
  $("foot").classList.toggle("stale", !!s.stale);
}
async function load(){
  try{
    const r = await fetch("/api/companion/characters/"+encodeURIComponent(CHAR), {credentials:"same-origin"});
    if (!r.ok) throw new Error("HTTP "+r.status);
    render(await r.json());
  }catch(e){ $("foot").textContent = "Couldn't load: "+e.message; $("foot").classList.add("stale"); }
}
load(); setInterval(load, 60000);
</script>
</body></html>"""


def render_page(character: str, nonce: str) -> str:
    return PAGE.replace("__NONCE__", nonce or "").replace("__CHAR__", json.dumps(character))

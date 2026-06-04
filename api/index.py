from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import json, sqlite3, uvicorn
from datetime import datetime, date
from pathlib import Path
import os

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DB = Path("followup.db")

def init_db():
    conn = sqlite3.connect(str(DB))
    conn.execute("""CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, source TEXT, note TEXT, deal_value INTEGER DEFAULT 0,
        status TEXT DEFAULT 'warm', follow_up_date TEXT, last_contacted TEXT,
        created TEXT, updated TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER, action TEXT, note TEXT, created TEXT
    )""")
    conn.commit()
    return conn

init_db()

def get_today_leads():
    today = date.today().isoformat()
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM leads WHERE follow_up_date <= ? AND status NOT IN ('lost','closed') ORDER BY follow_up_date ASC", (today,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_overdue_leads():
    today = date.today().isoformat()
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM leads WHERE follow_up_date < ? AND status NOT IN ('lost','closed') ORDER BY follow_up_date ASC", (today,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_active_leads():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM leads WHERE status NOT IN ('lost','closed') ORDER BY follow_up_date ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_lost_leads():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM leads WHERE status IN ('lost','closed') ORDER BY updated DESC LIMIT 30").fetchall()
    conn.close()
    return [dict(r) for r in rows]

HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Follow-Up OS</title>
<style>
:root{--bg:#050508;--surface:#0b0b14;--border:#1e1e30;--text:#d4d4d8;--muted:#71717a;--accent:#ff6b35;--success:#22c55e;--warn:#f59e0b;--danger:#ef4444}
*{margin:0;padding:0;box-sizing:border-box}
body <a href="https://hits.seeyoufarm.com"><img src="https://hits.seeyoufarm.com/api/count/incr/badge.svg?url=https%3A%2F%2Ffollow-up-os-production.up.railway.app&count_bg=%23FF6B35&title_bg=%23050508&icon=&icon_color=%23E7E7E7&title=visitors&edge_flat=false"/></a>{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;padding:20px}
.container{max-width:900px;margin:0 auto}
h1{font-size:1.5rem;color:#fff;text-align:center}h1 span{color:var(--accent)}
p.sub{color:var(--muted);text-align:center;margin-bottom:20px;font-size:0.8rem}
.tabs{display:flex;gap:4px;margin-bottom:20px;flex-wrap:wrap}
.tab{flex:1;min-width:100px;text-align:center;padding:10px 8px;border-radius:10px;cursor:pointer;font-weight:600;font-size:0.75rem;color:var(--muted);background:var(--surface);border:1px solid var(--border);transition:.2s}
.tab.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.tab .count{background:#fff;color:var(--accent);padding:1px 7px;border-radius:8px;font-size:0.65rem;margin-left:4px;font-weight:800}
.panel{display:none}.panel.active{display:block}
.card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:24px;margin-bottom:16px}
.card h3{color:var(--accent);font-size:0.75rem;text-transform:uppercase;letter-spacing:2px;margin-bottom:16px}
label{display:block;color:var(--muted);font-size:0.65rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px}
input,textarea,select{width:100%;background:var(--bg);border:1px solid var(--border);color:#fff;padding:12px;border-radius:10px;font-size:0.9rem;font-family:inherit;outline:none;margin-bottom:12px}
textarea{resize:vertical;min-height:60px}
input:focus,textarea:focus,select:focus{border-color:var(--accent)}
.btn{background:var(--accent);color:#fff;border:none;padding:14px;border-radius:24px;font-weight:700;font-size:0.9rem;cursor:pointer;width:100%}
.btn:hover{opacity:0.9}.btn:disabled{opacity:0.4}
.btn-sm{background:var(--accent);color:#fff;border:none;padding:8px 16px;border-radius:14px;font-size:0.75rem;cursor:pointer;font-weight:600}
.btn-danger{background:var(--danger)}.btn-success{background:var(--success)}.btn-warn{background:var(--warn);color:#000}
.lead-row{background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:16px;margin:8px 0;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}
.lead-row .info{flex:1;min-width:180px}
.lead-row .name{color:#fff;font-weight:600;font-size:0.95rem}
.lead-row .detail{color:var(--muted);font-size:0.75rem;margin-top:2px}
.lead-row .actions{display:flex;gap:6px;flex-wrap:wrap}
.badge{display:inline-block;padding:3px 10px;border-radius:10px;font-size:0.65rem;font-weight:700}
.badge.hot{background:#22c55e20;color:var(--success)}.badge.warm{background:#f59e0b20;color:var(--warn)}
.badge.cold{background:#ef444420;color:var(--danger)}.badge.lost{background:#88888820;color:var(--muted)}.badge.closed{background:#22c55e40;color:#fff}
.overdue{border-left:4px solid var(--danger)}.today{border-left:4px solid var(--accent)}
.empty{text-align:center;color:var(--muted);padding:40px;font-size:0.9rem}
.spinner{display:inline-block;width:14px;height:14px;border:2px solid #fff3;border-top-color:#fff;border-radius:50%;animation:spin .6s linear infinite;margin-right:8px;vertical-align:middle}
@keyframes spin{to{transform:rotate(360deg)}}
.summary{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap}
.summary-card{flex:1;min-width:120px;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px;text-align:center}
.summary-card .num{font-size:2rem;font-weight:800}
.summary-card .lbl{color:var(--muted);font-size:0.7rem;text-transform:uppercase;letter-spacing:1px}
.summary-card.today{border-color:var(--accent)}.summary-card.today .num{color:var(--accent)}
.summary-card.overdue{border-color:var(--danger)}.summary-card.overdue .num{color:var(--danger)}
.summary-card.active{border-color:var(--success)}.summary-card.active .num{color:var(--success)}
</style>
</head>
<body>
<div class="container">
<h1>📱 <span>Follow-Up</span> OS</h1>
<p class="sub">Never lose money from forgotten leads again.</p>

<div class="summary" id="summary"></div>

<div class="tabs">
<div class="tab active" onclick="switchTab('add')">➕ Add Lead</div>
<div class="tab" onclick="switchTab('today')">🔥 Today<span class="count" id="todayCount">0</span></div>
<div class="tab" onclick="switchTab('active')">📊 Active<span class="count" id="activeCount">0</span></div>
<div class="tab" onclick="switchTab('lost')">📁 Closed/Lost</div>
</div>

<div id="add" class="panel active">
<div class="card">
<h3>New Lead</h3>
<label>Name *</label><input id="l_name" placeholder="Client name">
<label>Source</label><select id="l_source"><option>Instagram</option><option>WhatsApp</option><option>Referral</option><option>Other</option></select>
<label>Note</label><textarea id="l_note" placeholder="What do they need?"></textarea>
<label>Deal Value (₦)</label><input id="l_value" placeholder="e.g. 150000" type="number">
<label>Status</label><select id="l_status"><option value="hot">🔥 Hot</option><option value="warm" selected>🟡 Warm</option><option value="cold">🔴 Cold</option></select>
<label>Follow-up Date</label><input id="l_date" type="date">
<button class="btn" id="addBtn" onclick="addLead()">Save Lead</button>
</div>
</div>

<div id="today" class="panel"><div class="card"><h3>🔥 Today's Follow-ups</h3><div id="todayList"><div class="empty">Loading...</div></div></div></div>
<div id="active" class="panel"><div class="card"><h3>📊 All Active Leads</h3><div id="activeList"><div class="empty">Loading...</div></div></div></div>
<div id="lost" class="panel"><div class="card"><h3>📁 Closed & Lost</h3><div id="lostList"><div class="empty">Loading...</div></div></div></div>
</div>

<script>
let current='add';
function switchTab(t){
current=t;document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));
document.getElementById(t).classList.add('active');
document.querySelector('.tab:nth-child('+(t==='add'?1:t==='today'?2:t==='active'?3:4)+')').classList.add('active');
if(t==='today')loadToday();if(t==='active')loadActive();if(t==='lost')loadLost();loadSummary();
}
function loadSummary(){
fetch('/api/summary').then(r=>r.json()).then(d=>{
document.getElementById('summary').innerHTML='<div class="summary-card today"><div class="num">'+d.today+'</div><div class="lbl">Due Today</div></div><div class="summary-card overdue"><div class="num">'+d.overdue+'</div><div class="lbl">Overdue</div></div><div class="summary-card active"><div class="num">'+d.active+'</div><div class="lbl">Active</div></div>';
document.getElementById('todayCount').textContent=d.today;document.getElementById('activeCount').textContent=d.active;
});
}
function renderLeads(leads,container){
let h='';if(!leads.length)h='<div class="empty">Nothing here. Great job!</div>';
leads.forEach(l=>{
let cls='';if(l.follow_up_date < new Date().toISOString().split('T')[0])cls='overdue';else if(l.follow_up_date === new Date().toISOString().split('T')[0])cls='today';
h+='<div class="lead-row '+cls+'"><div class="info"><div class="name">'+l.name+' <span class="badge '+l.status+'">'+l.status.toUpperCase()+'</span></div>';
h+='<div class="detail">💰 ₦'+(l.deal_value||0).toLocaleString()+' | 📅 Follow-up: '+l.follow_up_date+' | 📝 '+l.note+'</div></div>';
h+='<div class="actions">';
if(l.status!=='lost'&&l.status!=='closed'){h+='<button class="btn-sm btn-success" onclick="updateStatus('+l.id+',\'closed\')">✅ Won</button>';h+='<button class="btn-sm btn-danger" onclick="updateStatus('+l.id+',\'lost\')">❌ Lost</button>';h+='<button class="btn-sm btn-warn" onclick="followedUp('+l.id+')">📞 Followed Up</button>';}
h+='</div></div>';
});
document.getElementById(container).innerHTML=h;
}
function loadToday(){fetch('/api/leads/today').then(r=>r.json()).then(d=>renderLeads(d,'todayList'))}
function loadActive(){fetch('/api/leads/active').then(r=>r.json()).then(d=>renderLeads(d,'activeList'))}
function loadLost(){fetch('/api/leads/lost').then(r=>r.json()).then(d=>renderLeads(d,'lostList'))}

async function addLead(){
const btn=document.getElementById('addBtn');const orig=btn.innerHTML;
btn.disabled=true;btn.innerHTML='<span class="spinner"></span>Saving...';
const r=await fetch('/api/leads',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({name:document.getElementById('l_name').value,source:document.getElementById('l_source').value,note:document.getElementById('l_note').value,deal_value:document.getElementById('l_value').value,status:document.getElementById('l_status').value,follow_up_date:document.getElementById('l_date').value})});
document.getElementById('l_name').value='';document.getElementById('l_note').value='';document.getElementById('l_value').value='';
btn.disabled=false;btn.innerHTML=orig;loadSummary();alert('Lead saved!');
}
async function updateStatus(id,status){
await fetch('/api/leads/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})});
if(current==='today')loadToday();else if(current==='active')loadActive();else if(current==='lost')loadLost();loadSummary();
}
async function followedUp(id){
let newDate=new Date();newDate.setDate(newDate.getDate()+3);
await fetch('/api/leads/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({follow_up_date:newDate.toISOString().split('T')[0],last_contacted:new Date().toISOString()})});
if(current==='today')loadToday();else if(current==='active')loadActive();loadSummary();
}

document.getElementById('l_date').value=new Date().toISOString().split('T')[0];
loadSummary();
</script>
</body></html>"""

@app.get("/", response_class=HTMLResponse)
async def home(): return HTML

@app.get("/api/summary")
async def summary():
    today = get_today_leads()
    overdue = get_overdue_leads()
    active = get_active_leads()
    return {"today": len(today), "overdue": len(overdue), "active": len(active)}

@app.post("/api/leads")
async def add_lead(req: Request):
    data = await req.json()
    conn = sqlite3.connect(str(DB))
    now = datetime.now().isoformat()
    conn.execute("INSERT INTO leads (name,source,note,deal_value,status,follow_up_date,created,updated) VALUES (?,?,?,?,?,?,?,?)",
        (data.get("name",""), data.get("source",""), data.get("note",""), data.get("deal_value",0), data.get("status","warm"), data.get("follow_up_date",date.today().isoformat()), now, now))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/api/leads/today")
async def today(): return get_today_leads()

@app.get("/api/leads/active")
async def active(): return get_active_leads()

@app.get("/api/leads/lost")
async def lost(): return get_lost_leads()

@app.put("/api/leads/{lead_id}")
async def update_lead(lead_id: int, req: Request):
    data = await req.json()
    conn = sqlite3.connect(str(DB))
    now = datetime.now().isoformat()
    for key in ["status","follow_up_date","last_contacted"]:
        if key in data:
            conn.execute(f"UPDATE leads SET {key}=?, updated=? WHERE id=?", (data[key], now, lead_id))
    conn.execute("INSERT INTO history (lead_id,action,note,created) VALUES (?,?,?,?)",
        (lead_id, data.get("status","updated"), data.get("note",""), now))
    conn.commit()
    conn.close()
    return {"ok": True}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import json, sqlite3, os, uuid
from datetime import datetime, date
from pathlib import Path
import urllib.request
import urllib.parse

app = FastAPI()
@app.get("/debug")
async def debug():
    return {
        "client_id_exists": bool(GOOGLE_CLIENT_ID),
        "client_id_first10": GOOGLE_CLIENT_ID[:10] if GOOGLE_CLIENT_ID else "MISSING",
        "secret_exists": bool(GOOGLE_CLIENT_SECRET),
        "redirect": REDIRECT_URI
    }
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DB = Path("followup.db")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID") or os.environ.get("google_client_id", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET") or os.environ.get("google_client_secret", "")
SITE_URL = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "follow-up-os-production.up.railway.app")
REDIRECT_URI = f"https://{SITE_URL}/auth/google/callback"

def init_db():
    conn = sqlite3.connect(str(DB))
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        name TEXT, picture TEXT, google_id TEXT,
        token TEXT, created TEXT, last_login TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL, source TEXT, note TEXT, deal_value INTEGER DEFAULT 0,
        status TEXT DEFAULT 'warm', follow_up_date TEXT, last_contacted TEXT,
        created TEXT, updated TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER, user_id INTEGER, action TEXT, note TEXT, created TEXT
    )""")
    conn.commit()
    return conn

init_db()

def get_user(request: Request):
    token = request.cookies.get("token")
    if not token: return None
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    user = conn.execute("SELECT * FROM users WHERE token=?", (token,)).fetchone()
    conn.close()
    return dict(user) if user else None

def get_today_leads(user_id):
    today = date.today().isoformat()
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM leads WHERE user_id=? AND follow_up_date <= ? AND status NOT IN ('lost','closed') ORDER BY follow_up_date ASC", (user_id, today)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_overdue_leads(user_id):
    today = date.today().isoformat()
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM leads WHERE user_id=? AND follow_up_date < ? AND status NOT IN ('lost','closed') ORDER BY follow_up_date ASC", (user_id, today)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_active_leads(user_id):
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM leads WHERE user_id=? AND status NOT IN ('lost','closed') ORDER BY follow_up_date ASC", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_lost_leads(user_id):
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM leads WHERE user_id=? AND status IN ('lost','closed') ORDER BY updated DESC LIMIT 30", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

LOGIN_PAGE = r"""
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Follow-Up OS</title>
<style>
:root{--bg:#050508;--surface:#0b0b14;--border:#1e1e30;--text:#d4d4d8;--muted:#71717a;--accent:#ff6b35}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:40px 32px;width:100%;max-width:380px;text-align:center}
h1{font-size:1.8rem;color:#fff;margin-bottom:8px}h1 span{color:var(--accent)}
p{color:var(--muted);font-size:0.9rem;margin-bottom:32px;line-height:1.5}
.google-btn{display:flex;align-items:center;justify-content:center;gap:12px;background:#fff;color:#333;border:none;padding:14px 24px;border-radius:12px;font-size:1rem;font-weight:600;cursor:pointer;width:100%;transition:.2s}
.google-btn:hover{background:#f0f0f0}
.google-btn img{width:20px;height:20px}
.footer{color:var(--muted);font-size:0.7rem;margin-top:24px}
</style></head><body>
<div class="card">
<h1>📱 <span>Follow-Up</span> OS</h1>
<p>Track your leads. Never forget a follow-up. Close more deals.</p>
<button class="google-btn" onclick="window.location.href='/auth/google'">
<svg width="20" height="20" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
Continue with Google
</button>
<div class="footer">Your leads are private. Only you see them.</div>
</div></body></html>"""

APP_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Follow-Up OS</title>
<style>
:root{--bg:#050508;--surface:#0b0b14;--border:#1e1e30;--text:#d4d4d8;--muted:#71717a;--accent:#ff6b35;--success:#22c55e;--warn:#f59e0b;--danger:#ef4444}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;padding:20px}
.container{max-width:900px;margin:0 auto}
.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}
.topbar h1{font-size:1.3rem;color:#fff}.topbar h1 span{color:var(--accent)}
.topbar .user-info{display:flex;align-items:center;gap:10px}
.topbar .user-info img{width:28px;height:28px;border-radius:50%}
.topbar .logout{color:var(--muted);text-decoration:none;font-size:0.8rem}
.summary{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap}
.summary-card{flex:1;min-width:120px;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px;text-align:center}
.summary-card .num{font-size:2rem;font-weight:800}
.summary-card .lbl{color:var(--muted);font-size:0.7rem;text-transform:uppercase;letter-spacing:1px}
.summary-card.today{border-color:var(--accent)}.summary-card.today .num{color:var(--accent)}
.summary-card.overdue{border-color:var(--danger)}.summary-card.overdue .num{color:var(--danger)}
.summary-card.active{border-color:var(--success)}.summary-card.active .num{color:var(--success)}
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
</style>
</head>
<body>
<div class="container">
<div class="topbar">
<h1>📱 <span>Follow-Up</span> OS</h1>
<div class="user-info">
<img id="userPic" src="" onerror="this.style.display='none'">
<span style="color:var(--muted);font-size:0.8rem" id="userName"></span>
<a href="/api/logout" class="logout">Logout</a>
</div>
</div>
<div class="summary" id="summary"></div>
<div class="tabs">
<div class="tab active" onclick="switchTab('add')">➕ Add Lead</div>
<div class="tab" onclick="switchTab('today')">🔥 Today<span class="count" id="todayCount">0</span></div>
<div class="tab" onclick="switchTab('active')">📊 Active<span class="count" id="activeCount">0</span></div>
<div class="tab" onclick="switchTab('lost')">📁 Closed/Lost</div>
</div>
<div id="add" class="panel active">
<div class="card"><h3>New Lead</h3>
<label>Name *</label><input id="l_name" placeholder="Client name">
<label>Source</label><select id="l_source"><option>Instagram</option><option>WhatsApp</option><option>Referral</option><option>Other</option></select>
<label>Note</label><textarea id="l_note" placeholder="What do they need?"></textarea>
<label>Deal Value (₦)</label><input id="l_value" placeholder="e.g. 150000" type="number">
<label>Status</label><select id="l_status"><option value="hot">🔥 Hot</option><option value="warm" selected>🟡 Warm</option><option value="cold">🔴 Cold</option></select>
<label>Follow-up Date</label><input id="l_date" type="date">
<button class="btn" id="addBtn" onclick="addLead()">Save Lead</button></div></div>
<div id="today" class="panel"><div class="card"><h3>🔥 Today's Follow-ups</h3><div id="todayList"><div class="empty">Loading...</div></div></div></div>
<div id="active" class="panel"><div class="card"><h3>📊 All Active Leads</h3><div id="activeList"><div class="empty">Loading...</div></div></div></div>
<div id="lost" class="panel"><div class="card"><h3>📁 Closed & Lost</h3><div id="lostList"><div class="empty">Loading...</div></div></div></div>
</div>
<script>
let current='add';
fetch('/api/me').then(r=>r.json()).then(d=>{
if(d.name)document.getElementById('userName').textContent=d.name;
if(d.picture)document.getElementById('userPic').src=d.picture;
});
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
let h='';if(!leads.length)h='<div class="empty">Nothing here.</div>';
leads.forEach(l=>{
let cls='';if(l.follow_up_date < new Date().toISOString().split('T')[0])cls='overdue';else if(l.follow_up_date === new Date().toISOString().split('T')[0])cls='today';
h+='<div class="lead-row '+cls+'"><div class="info"><div class="name">'+l.name+' <span class="badge '+l.status+'">'+l.status.toUpperCase()+'</span></div>';
h+='<div class="detail">💰 ₦'+(l.deal_value||0).toLocaleString()+' | 📅 '+l.follow_up_date+' | 📝 '+l.note+'</div></div>';
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
async def home(request: Request):
    user = get_user(request)
    if user: return RedirectResponse("/app")
    return LOGIN_PAGE

@app.get("/app", response_class=HTMLResponse)
async def app_page(request: Request):
    user = get_user(request)
    if not user: return RedirectResponse("/")
    return APP_HTML

@app.get("/auth/google")
async def auth_google():
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent"
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return RedirectResponse(url)

@app.get("/auth/google/callback")
async def auth_google_callback(code: str):
    token_url = "https://oauth2.googleapis.com/token"
    token_data = urllib.parse.urlencode({
        "code": code, "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code"
    }).encode()
    req = urllib.request.Request(token_url, data=token_data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    token_resp = json.loads(urllib.request.urlopen(req).read())
    access_token = token_resp.get("access_token")
    
    user_req = urllib.request.Request("https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": f"Bearer {access_token}"})
    user_info = json.loads(urllib.request.urlopen(user_req).read())
    
    email = user_info.get("email")
    name = user_info.get("name", "")
    picture = user_info.get("picture", "")
    google_id = user_info.get("id", "")
    
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    existing = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    token = str(uuid.uuid4())
    
    if existing:
        conn.execute("UPDATE users SET name=?, picture=?, token=?, last_login=? WHERE id=?",
            (name, picture, token, datetime.now().isoformat(), existing["id"]))
    else:
        conn.execute("INSERT INTO users (email,name,picture,google_id,token,created,last_login) VALUES (?,?,?,?,?,?,?)",
            (email, name, picture, google_id, token, datetime.now().isoformat(), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    response = RedirectResponse("/app")
    response.set_cookie("token", token, httponly=True, max_age=86400*30)
    return response

@app.get("/api/me")
async def me(request: Request):
    user = get_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return {"name": user.get("name",""), "email": user.get("email",""), "picture": user.get("picture","")}

@app.get("/api/logout")
async def logout():
    response = RedirectResponse("/")
    response.delete_cookie("token")
    return response

@app.get("/api/summary")
async def summary(request: Request):
    user = get_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return {"today": len(get_today_leads(user["id"])), "overdue": len(get_overdue_leads(user["id"])), "active": len(get_active_leads(user["id"]))}

@app.post("/api/leads")
async def add_lead(request: Request):
    user = get_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    data = await request.json()
    conn = sqlite3.connect(str(DB))
    now = datetime.now().isoformat()
    conn.execute("INSERT INTO leads (user_id,name,source,note,deal_value,status,follow_up_date,created,updated) VALUES (?,?,?,?,?,?,?,?,?)",
        (user["id"], data.get("name",""), data.get("source",""), data.get("note",""), data.get("deal_value",0), data.get("status","warm"), data.get("follow_up_date",date.today().isoformat()), now, now))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/api/leads/today")
async def today(request: Request):
    user = get_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return get_today_leads(user["id"])

@app.get("/api/leads/active")
async def active(request: Request):
    user = get_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return get_active_leads(user["id"])

@app.get("/api/leads/lost")
async def lost(request: Request):
    user = get_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return get_lost_leads(user["id"])

@app.put("/api/leads/{lead_id}")
async def update_lead(lead_id: int, request: Request):
    user = get_user(request)
    if not user: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    data = await request.json()
    conn = sqlite3.connect(str(DB))
    now = datetime.now().isoformat()
    for key in ["status","follow_up_date","last_contacted"]:
        if key in data:
            conn.execute(f"UPDATE leads SET {key}=?, updated=? WHERE id=? AND user_id=?", (data[key], now, lead_id, user["id"]))
    conn.execute("INSERT INTO history (lead_id,user_id,action,note,created) VALUES (?,?,?,?,?)",
        (lead_id, user["id"], data.get("status","updated"), data.get("note",""), now))
    conn.commit()
    conn.close()
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
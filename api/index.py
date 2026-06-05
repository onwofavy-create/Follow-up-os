from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import json, sqlite3, uuid, bcrypt, os
from datetime import datetime, date
from pathlib import Path

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DB = Path("followup.db")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

@app.middleware("http")
async def add_session(request: Request, call_next):
    response = await call_next(request)
    if not request.cookies.get("session_id") and not request.cookies.get("token"):
        response.set_cookie("session_id", str(uuid.uuid4()), httponly=True, max_age=86400)
    return response

def init_db():
    conn = sqlite3.connect(str(DB))
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        token TEXT, created TEXT, last_login TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL DEFAULT 0,
        session_id TEXT DEFAULT '0',
        name TEXT NOT NULL, source TEXT, note TEXT, deal_value INTEGER DEFAULT 0,
        status TEXT DEFAULT 'warm', follow_up_date TEXT, last_contacted TEXT,
        created TEXT, updated TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER, user_id INTEGER, action TEXT, note TEXT, created TEXT
    )""")
    try: conn.execute("ALTER TABLE leads ADD COLUMN session_id TEXT DEFAULT '0'")
    except: pass
    conn.commit()
    return conn

init_db()

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())

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
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Follow-Up OS</title>
<style>
:root{--bg:#050508;--surface:#0b0b14;--border:#1e1e30;--text:#d4d4d8;--muted:#71717a;--accent:#ff6b35}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:32px;width:100%;max-width:380px;text-align:center}
h1{font-size:1.5rem;color:#fff;margin-bottom:8px}h1 span{color:var(--accent)}
p{color:var(--muted);font-size:0.85rem;margin-bottom:24px}
input{width:100%;background:var(--bg);border:1px solid var(--border);color:#fff;padding:12px;border-radius:10px;font-size:0.9rem;margin-bottom:12px;outline:none}
input:focus{border-color:var(--accent)}
.btn{background:var(--accent);color:#fff;border:none;padding:14px;border-radius:24px;font-weight:700;font-size:0.9rem;cursor:pointer;width:100%}
.btn:hover{opacity:0.9}
.error{color:#ef4444;font-size:0.8rem;margin-bottom:12px}
.link{color:var(--muted);font-size:0.8rem;margin-top:12px;display:block}
</style></head><body>
<div class="card"><h1>📱 <span>Follow-Up</span> OS</h1><p>Login to see your leads</p>
<div id="error" class="error"></div>
<form onsubmit="login(event)"><input type="email" id="email" placeholder="Email" required>
<input type="password" id="password" placeholder="Password" required><button class="btn">Login</button></form>
<a href="/signup" class="link">Don't have an account? Create one</a></div>
<script>async function login(e){e.preventDefault();const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:document.getElementById('email').value,password:document.getElementById('password').value})});if(r.ok){window.location.href='/app'}else{const d=await r.json();document.getElementById('error').textContent=d.error}}</script>
</body></html>"""

SIGNUP_PAGE = r"""
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Follow-Up OS - Sign Up</title>
<style>:root{--bg:#050508;--surface:#0b0b14;--border:#1e1e30;--text:#d4d4d8;--muted:#71717a;--accent:#ff6b35}
*{margin:0;padding:0;box-sizing:border-box}body{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:32px;width:100%;max-width:380px;text-align:center}
h1{font-size:1.5rem;color:#fff;margin-bottom:8px}h1 span{color:var(--accent)}
p{color:var(--muted);font-size:0.85rem;margin-bottom:24px}
input{width:100%;background:var(--bg);border:1px solid var(--border);color:#fff;padding:12px;border-radius:10px;font-size:0.9rem;margin-bottom:12px;outline:none}input:focus{border-color:var(--accent)}
.btn{background:var(--accent);color:#fff;border:none;padding:14px;border-radius:24px;font-weight:700;font-size:0.9rem;cursor:pointer;width:100%}.btn:hover{opacity:0.9}
.error{color:#ef4444;font-size:0.8rem;margin-bottom:12px}.link{color:var(--muted);font-size:0.8rem;margin-top:12px;display:block}
</style></head><body><div class="card"><h1>📱 <span>Follow-Up</span> OS</h1><p>Create your free account</p>
<div id="error" class="error"></div><form onsubmit="signup(event)"><input type="email" id="email" placeholder="Email" required>
<input type="password" id="password" placeholder="Create a password" minlength="6" required><button class="btn">Create Account</button></form>
<a href="/login" class="link">Already have an account? Login</a></div>
<script>async function signup(e){e.preventDefault();const r=await fetch('/api/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:document.getElementById('email').value,password:document.getElementById('password').value})});if(r.ok){window.location.href='/app'}else{const d=await r.json();document.getElementById('error').textContent=d.error}}</script>
</body></html>"""

APP_HTML = r"""
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Follow-Up OS</title>
<style>:root{--bg:#050508;--surface:#0b0b14;--border:#1e1e30;--text:#d4d4d8;--muted:#71717a;--accent:#ff6b35;--success:#22c55e;--warn:#f59e0b;--danger:#ef4444}
*{margin:0;padding:0;box-sizing:border-box}body{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;padding:20px}
.container{max-width:900px;margin:0 auto}.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}
.topbar h1{font-size:1.3rem;color:#fff}.topbar h1 span{color:var(--accent)}
.topbar .user-info{display:flex;align-items:center;gap:10px}.topbar .user-info span{color:var(--muted);font-size:0.8rem}
.topbar .logout{color:var(--muted);text-decoration:none;font-size:0.8rem}
.save-banner{background:var(--surface);border:1px solid var(--warn);border-radius:12px;padding:16px;margin-bottom:20px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;justify-content:center}
.save-banner input{background:var(--bg);border:1px solid var(--border);color:#fff;padding:10px;border-radius:8px;font-size:0.85rem}
.save-banner .btn-sm{padding:10px 16px;font-size:0.8rem;background:var(--accent);color:#fff;border:none;border-radius:8px;cursor:pointer}
.save-banner .warn{color:var(--warn);font-size:0.8rem}
.summary{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap}
.summary-card{flex:1;min-width:120px;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px;text-align:center}
.summary-card .num{font-size:2rem;font-weight:800}.summary-card .lbl{color:var(--muted);font-size:0.7rem;text-transform:uppercase;letter-spacing:1px}
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
textarea{resize:vertical;min-height:60px}input:focus,textarea:focus,select:focus{border-color:var(--accent)}
.btn{background:var(--accent);color:#fff;border:none;padding:14px;border-radius:24px;font-weight:700;font-size:0.9rem;cursor:pointer;width:100%}.btn:hover{opacity:0.9}.btn:disabled{opacity:0.4}
.btn-sm{background:var(--accent);color:#fff;border:none;padding:8px 16px;border-radius:14px;font-size:0.75rem;cursor:pointer;font-weight:600}
.btn-danger{background:var(--danger)}.btn-success{background:var(--success)}.btn-warn{background:var(--warn);color:#000}
.lead-row{background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:16px;margin:8px 0;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}
.lead-row .info{flex:1;min-width:180px}.lead-row .name{color:#fff;font-weight:600;font-size:0.95rem}
.lead-row .detail{color:var(--muted);font-size:0.75rem;margin-top:2px}.lead-row .actions{display:flex;gap:6px;flex-wrap:wrap}
.badge{display:inline-block;padding:3px 10px;border-radius:10px;font-size:0.65rem;font-weight:700}
.badge.hot{background:#22c55e20;color:var(--success)}.badge.warm{background:#f59e0b20;color:var(--warn)}
.badge.cold{background:#ef444420;color:var(--danger)}.badge.lost{background:#88888820;color:var(--muted)}.badge.closed{background:#22c55e40;color:#fff}
.overdue{border-left:4px solid var(--danger)}.today{border-left:4px solid var(--accent)}
.empty{text-align:center;color:var(--muted);padding:40px;font-size:0.9rem}
.spinner{display:inline-block;width:14px;height:14px;border:2px solid #fff3;border-top-color:#fff;border-radius:50%;animation:spin .6s linear infinite;margin-right:8px;vertical-align:middle}
@keyframes spin{to{transform:rotate(360deg)}}
</style></head><body><div class="container"><div class="topbar"><h1>📱 <span>Follow-Up</span> OS</h1>
<div class="user-info"><span id="userEmail"></span><a href="/api/logout" class="logout" id="logoutLink" style="display:none">Logout</a></div></div>
<div id="saveBanner" class="save-banner" style="display:none"><span class="warn">⚠️ Your leads will be lost when you close this tab.</span>
<input type="email" id="bannerEmail" placeholder="Email"><input type="password" id="bannerPassword" placeholder="Create password" minlength="6">
<button class="btn-sm" onclick="saveAccount()">Save My Leads</button><span id="bannerError" style="color:#ef4444;font-size:0.75rem"></span></div>
<div class="summary" id="summary"></div><div class="tabs">
<div class="tab active" onclick="switchTab('add')">➕ Add Lead</div><div class="tab" onclick="switchTab('today')">🔥 Today<span class="count" id="todayCount">0</span></div>
<div class="tab" onclick="switchTab('active')">📊 Active<span class="count" id="activeCount">0</span></div><div class="tab" onclick="switchTab('lost')">📁 Closed/Lost</div></div>
<div id="add" class="panel active"><div class="card"><h3>New Lead</h3><label>Name *</label><input id="l_name" placeholder="Client name">
<label>Source</label><select id="l_source"><option>Instagram</option><option>WhatsApp</option><option>Referral</option><option>Other</option></select>
<label>Note</label><textarea id="l_note" placeholder="What do they need?"></textarea><label>Deal Value (₦)</label><input id="l_value" placeholder="e.g. 150000" type="number">
<label>Status</label><select id="l_status"><option value="hot">🔥 Hot</option><option value="warm" selected>🟡 Warm</option><option value="cold">🔴 Cold</option></select>
<label>Follow-up Date</label><input id="l_date" type="date"><button class="btn" id="addBtn" onclick="addLead()">Save Lead</button></div></div>
<div id="today" class="panel"><div class="card"><h3>🔥 Today's Follow-ups</h3><div id="todayList"><div class="empty">Loading...</div></div></div></div>
<div id="active" class="panel"><div class="card"><h3>📊 All Active Leads</h3><div id="activeList"><div class="empty">Loading...</div></div></div></div>
<div id="lost" class="panel"><div class="card"><h3>📁 Closed & Lost</h3><div id="lostList"><div class="empty">Loading...</div></div></div></div></div>
<script>
let current='add',isLoggedIn=false;
fetch('/api/me').then(r=>r.json()).then(d=>{if(d.email){isLoggedIn=true;document.getElementById('userEmail').textContent=d.email;document.getElementById('logoutLink').style.display='inline';document.getElementById('saveBanner').style.display='none'}else{document.getElementById('saveBanner').style.display='flex'}loadSummary()});
function switchTab(t){current=t;document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));document.getElementById(t).classList.add('active');document.querySelector('.tab:nth-child('+(t==='add'?1:t==='today'?2:t==='active'?3:4)+')').classList.add('active');if(t==='today')loadToday();if(t==='active')loadActive();if(t==='lost')loadLost();loadSummary()}
function loadSummary(){fetch('/api/summary').then(r=>r.json()).then(d=>{document.getElementById('summary').innerHTML='<div class="summary-card today"><div class="num">'+d.today+'</div><div class="lbl">Due Today</div></div><div class="summary-card overdue"><div class="num">'+d.overdue+'</div><div class="lbl">Overdue</div></div><div class="summary-card active"><div class="num">'+d.active+'</div><div class="lbl">Active</div></div>';document.getElementById('todayCount').textContent=d.today;document.getElementById('activeCount').textContent=d.active})}
function renderLeads(leads,container){let h='';if(!leads.length)h='<div class="empty">Nothing here.</div>';leads.forEach(l=>{let cls='';if(l.follow_up_date<new Date().toISOString().split('T')[0])cls='overdue';else if(l.follow_up_date===new Date().toISOString().split('T')[0])cls='today';h+='<div class="lead-row '+cls+'"><div class="info"><div class="name">'+l.name+' <span class="badge '+l.status+'">'+l.status.toUpperCase()+'</span></div><div class="detail">💰 ₦'+(l.deal_value||0).toLocaleString()+' | 📅 '+l.follow_up_date+' | 📝 '+l.note+'</div></div><div class="actions">';if(l.status!=='lost'&&l.status!=='closed'){h+='<button class="btn-sm btn-success" onclick="updateStatus('+l.id+',\'closed\')">✅ Won</button>';h+='<button class="btn-sm btn-danger" onclick="updateStatus('+l.id+',\'lost\')">❌ Lost</button>';h+='<button class="btn-sm btn-warn" onclick="followedUp('+l.id+')">📞 Followed Up</button>'}h+='</div></div>'});document.getElementById(container).innerHTML=h}
function loadToday(){fetch('/api/leads/today').then(r=>r.json()).then(d=>renderLeads(d,'todayList'))}
function loadActive(){fetch('/api/leads/active').then(r=>r.json()).then(d=>renderLeads(d,'activeList'))}
function loadLost(){fetch('/api/leads/lost').then(r=>r.json()).then(d=>renderLeads(d,'lostList'))}
async function saveAccount(){const email=document.getElementById('bannerEmail').value;const password=document.getElementById('bannerPassword').value;if(!email||password.length<6){document.getElementById('bannerError').textContent='Email and password (6+ chars) required';return}const r=await fetch('/api/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});if(r.ok){location.reload()}else{const d=await r.json();document.getElementById('bannerError').textContent=d.error}}
async function addLead(){const btn=document.getElementById('addBtn');const orig=btn.innerHTML;btn.disabled=true;btn.innerHTML='<span class="spinner"></span>Saving...';const r=await fetch('/api/leads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:document.getElementById('l_name').value,source:document.getElementById('l_source').value,note:document.getElementById('l_note').value,deal_value:document.getElementById('l_value').value,status:document.getElementById('l_status').value,follow_up_date:document.getElementById('l_date').value})});document.getElementById('l_name').value='';document.getElementById('l_note').value='';document.getElementById('l_value').value='';btn.disabled=false;btn.innerHTML=orig;loadSummary();if(!isLoggedIn)document.getElementById('saveBanner').style.display='flex'}
async function updateStatus(id,status){await fetch('/api/leads/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})});if(current==='today')loadToday();else if(current==='active')loadActive();else if(current==='lost')loadLost();loadSummary()}
async function followedUp(id){let newDate=new Date();newDate.setDate(newDate.getDate()+3);await fetch('/api/leads/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({follow_up_date:newDate.toISOString().split('T')[0],last_contacted:new Date().toISOString()})});if(current==='today')loadToday();else if(current==='active')loadActive();loadSummary()}
document.getElementById('l_date').value=new Date().toISOString().split('T')[0];loadSummary();
</script></body></html>"""

ADMIN_HTML = r"""
<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Admin</title>
<style>body{font-family:system-ui;background:#050508;color:#d4d4d8;padding:40px}table{width:100%;border-collapse:collapse}th,td{padding:12px;text-align:left;border-bottom:1px solid #1e1e30}th{color:#ff6b35}</style></head><body>
<h1>Admin Panel</h1><table><tr><th>Email</th><th>Leads</th><th>Signed Up</th><th>Last Login</th></tr><tbody id="users"></tbody></table>
<script>fetch('/api/admin/users').then(r=>r.json()).then(users=>{let h='';users.forEach(u=>{h+=`<tr><td>${u.email}</td><td>${u.lead_count}</td><td>${u.created}</td><td>${u.last_login}</td></tr>`});document.getElementById('users').innerHTML=h})</script></body></html>"""

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = get_user(request)
    if user: return RedirectResponse("/app")
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_user(request): return RedirectResponse("/app")
    return LOGIN_PAGE

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(): return SIGNUP_PAGE

@app.get("/app", response_class=HTMLResponse)
async def app_page(): return APP_HTML

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    if request.cookies.get("admin_token") == ADMIN_PASSWORD:
        return ADMIN_HTML
    return """<html><body style="background:#050508;color:#fff;font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh"><form method="post" action="/admin/login"><input name="password" type="password" placeholder="Admin password" style="padding:12px;background:#0b0b14;border:1px solid #1e1e30;color:#fff;border-radius:8px"><button style="margin-top:8px;padding:12px 24px;background:#ff6b35;color:#fff;border:none;border-radius:8px;cursor:pointer">Access Admin</button></form></body></html>"""

@app.post("/admin/login")
async def admin_login(request: Request):
    data = await request.form()
    if data.get("password") == ADMIN_PASSWORD:
        resp = RedirectResponse("/admin", status_code=303)
        resp.set_cookie("admin_token", ADMIN_PASSWORD, httponly=True)
        return resp
    return RedirectResponse("/admin")

@app.get("/api/me")
async def me(request: Request):
    user = get_user(request)
    if not user: return JSONResponse({"email": None})
    return {"id": user["id"], "email": user["email"]}

@app.post("/api/signup")
async def signup(request: Request):
    data = await request.json()
    email = data.get("email","").strip().lower()
    password = data.get("password","").strip()
    if not email or len(password) < 6:
        return JSONResponse({"error": "Email and 6+ char password required"}, status_code=400)
    conn = sqlite3.connect(str(DB))
    try:
        token = str(uuid.uuid4())
        conn.execute("INSERT INTO users (email,password,token,created,last_login) VALUES (?,?,?,?,?)",
            (email, hash_password(password), token, datetime.now().isoformat(), datetime.now().isoformat()))
        conn.execute("UPDATE leads SET user_id=(SELECT id FROM users WHERE token=?) WHERE user_id=0 AND session_id=?",
            (token, request.cookies.get("session_id","")))
        conn.commit()
        resp = JSONResponse({"ok": True})
        resp.set_cookie("token", token, httponly=True, max_age=86400*365)
        return resp
    except sqlite3.IntegrityError:
        return JSONResponse({"error": "Email already registered"}, status_code=400)
    finally:
        conn.close()

@app.post("/api/login")
async def login(request: Request):
    data = await request.json()
    email = data.get("email","").strip().lower()
    password = data.get("password","").strip()
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    user_row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not user_row or not check_password(password, user_row["password"]):
        conn.close()
        return JSONResponse({"error": "Invalid email or password"}, status_code=401)
    token = str(uuid.uuid4())
    conn.execute("UPDATE users SET token=?, last_login=? WHERE id=?", (token, datetime.now().isoformat(), user_row["id"]))
    conn.commit()
    conn.close()
    resp = JSONResponse({"ok": True})
    resp.set_cookie("token", token, httponly=True, max_age=86400*365)
    return resp

@app.get("/api/logout")
async def logout():
    resp = RedirectResponse("/login")
    resp.delete_cookie("token")
    return resp

@app.get("/api/summary")
async def summary(request: Request):
    user = get_user(request)
    uid = user["id"] if user else 0
    return {"today": len(get_today_leads(uid)), "overdue": len(get_overdue_leads(uid)), "active": len(get_active_leads(uid))}

@app.post("/api/leads")
async def add_lead(request: Request):
    user = get_user(request)
    uid = user["id"] if user else 0
    session_id = request.cookies.get("session_id", "0")
    data = await request.json()
    conn = sqlite3.connect(str(DB))
    now = datetime.now().isoformat()
    conn.execute("INSERT INTO leads (user_id,session_id,name,source,note,deal_value,status,follow_up_date,created,updated) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (uid, session_id, data.get("name",""), data.get("source",""), data.get("note",""), data.get("deal_value",0), data.get("status","warm"), data.get("follow_up_date",date.today().isoformat()), now, now))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/api/leads/today")
async def today(request: Request):
    user = get_user(request)
    return get_today_leads(user["id"] if user else 0)

@app.get("/api/leads/active")
async def active(request: Request):
    user = get_user(request)
    return get_active_leads(user["id"] if user else 0)

@app.get("/api/leads/lost")
async def lost(request: Request):
    user = get_user(request)
    return get_lost_leads(user["id"] if user else 0)

@app.put("/api/leads/{lead_id}")
async def update_lead(lead_id: int, request: Request):
    user = get_user(request)
    uid = user["id"] if user else 0
    data = await request.json()
    conn = sqlite3.connect(str(DB))
    now = datetime.now().isoformat()
    for key in ["status","follow_up_date","last_contacted"]:
        if key in data:
            conn.execute(f"UPDATE leads SET {key}=?, updated=? WHERE id=? AND user_id=?", (data[key], now, lead_id, uid))
    conn.execute("INSERT INTO history (lead_id,user_id,action,note,created) VALUES (?,?,?,?,?)",
        (lead_id, uid, data.get("status","updated"), data.get("note",""), now))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/api/admin/users")
async def admin_users():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    users = conn.execute("SELECT id,email,created,last_login FROM users ORDER BY last_login DESC").fetchall()
    result = []
    for u in users:
        count = conn.execute("SELECT COUNT(*) FROM leads WHERE user_id=?", (u["id"],)).fetchone()[0]
        result.append({"email": u["email"], "lead_count": count, "created": u["created"][:10], "last_login": u["last_login"][:16] if u["last_login"] else "Never"})
    conn.close()
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
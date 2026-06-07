from fastapi import FastAPI, Request, Response, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import json, os, io, uuid, bcrypt, psycopg2, re
from datetime import datetime, date, timedelta

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DATABASE_URL = os.environ.get("DATABASE_URL", "")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "followup2024")

def connect_db():
    return psycopg2.connect(DATABASE_URL) if DATABASE_URL else None

def setup_db():
    if not DATABASE_URL: return
    conn = connect_db(); cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, token TEXT, streak INTEGER DEFAULT 0, last_streak_date TEXT, created TEXT, last_login TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS leads (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL DEFAULT 0, session_id TEXT DEFAULT '0', name TEXT NOT NULL, source TEXT, note TEXT, deal_value INTEGER DEFAULT 0, status TEXT DEFAULT 'warm', follow_up_date TEXT, last_contacted TEXT, nudge_enabled INTEGER DEFAULT 0, created TEXT, updated TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS history (id SERIAL PRIMARY KEY, lead_id INTEGER, user_id INTEGER, action TEXT, note TEXT, created TEXT)")
    conn.commit(); conn.close()

setup_db()

def hash_pw(password): return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
def check_pw(password, hashed): return bcrypt.checkpw(password.encode(), hashed.encode())

def fetch_user(request: Request):
    token = request.cookies.get("token")
    if not token or not DATABASE_URL: return None
    conn = connect_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE token=%s", (token,))
    row = cur.fetchone()
    conn.close()
    if row: return dict(zip(["id","email","password","token","streak","last_streak_date","created","last_login"], row))
    return None

def execute_query(query, params=()):
    if not DATABASE_URL: return []
    conn = connect_db(); cur = conn.cursor()
    cur.execute(query, params)
    if query.strip().upper().startswith("SELECT"):
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        conn.close()
        return [dict(zip(cols, r)) for r in rows]
    conn.commit(); conn.close()
    return []

def today_leads(user_id):
    today = date.today().isoformat()
    return execute_query("SELECT * FROM leads WHERE user_id=%s AND follow_up_date <= %s AND status NOT IN ('lost','closed') ORDER BY follow_up_date ASC", (user_id, today))

def overdue_leads(user_id):
    today = date.today().isoformat()
    return execute_query("SELECT * FROM leads WHERE user_id=%s AND follow_up_date < %s AND status NOT IN ('lost','closed') ORDER BY follow_up_date ASC", (user_id, today))

def active_leads(user_id):
    return execute_query("SELECT * FROM leads WHERE user_id=%s AND status NOT IN ('lost','closed') ORDER BY follow_up_date ASC", (user_id,))

def closed_leads(user_id):
    return execute_query("SELECT * FROM leads WHERE user_id=%s AND status IN ('lost','closed') ORDER BY updated DESC LIMIT 30", (user_id,))

HTML_PAGE = """<!DOCTYPE html>
<html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>Follow-Up OS</title>
<style>
:root{--bg:#06060e;--surface:#0c0c1a;--border:#1a1a35;--text:#e0e0e8;--muted:#7a7a90;--blue:#3b82f6;--orange:#ff6b35;--success:#22c55e;--warn:#f59e0b;--danger:#ef4444}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui;background:var(--bg);color:var(--text);min-height:100vh;padding:20px}
.container{max-width:900px;margin:0 auto}
.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}
.topbar h1{font-size:1.3rem;color:#fff}.topbar h1 span{color:var(--blue)}
.logout{color:var(--muted);text-decoration:none;font-size:.8rem}
.save-banner{background:var(--surface);border:1px solid var(--warn);border-radius:12px;padding:14px;margin-bottom:20px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;justify-content:center}
.save-banner span{color:var(--warn);font-weight:600;font-size:.8rem}
.save-banner input{background:var(--bg);border:1px solid var(--border);color:#fff;padding:8px 12px;border-radius:8px;font-size:.8rem}
.btn{background:var(--blue);color:#fff;border:none;padding:10px 18px;border-radius:8px;font-weight:600;cursor:pointer;font-size:.8rem}
.btn-orange{background:var(--orange)}.btn-success{background:var(--success)}.btn-danger{background:var(--danger)}.btn-warn{background:var(--warn);color:#000}
.btn-sm{padding:6px 12px;font-size:.7rem;border-radius:6px;border:none;cursor:pointer;font-weight:600}
.summary{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap}
.summary-card{flex:1;min-width:120px;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:18px;text-align:center}
.summary-card .num{font-size:2rem;font-weight:800}.summary-card .lbl{color:var(--muted);font-size:.65rem;text-transform:uppercase}
.tabs{display:flex;gap:4px;margin-bottom:20px}.tab{flex:1;text-align:center;padding:10px;border-radius:8px;cursor:pointer;background:var(--surface);border:1px solid var(--border);color:var(--muted);font-weight:600;font-size:.75rem}.tab.active{background:var(--blue);color:#fff}
.panel{display:none}.panel.active{display:block}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:16px}
.card h3{color:var(--muted);font-size:.7rem;text-transform:uppercase;margin-bottom:14px}
input,textarea,select{width:100%;background:var(--bg);border:1px solid var(--border);color:#fff;padding:10px;border-radius:8px;margin-bottom:10px;font-size:.85rem;font-family:inherit;outline:none}
label{display:block;color:var(--muted);font-size:.65rem;text-transform:uppercase;margin-bottom:3px}
.quick-chips{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:12px}
.chip{background:var(--surface);border:1px solid var(--border);color:var(--muted);padding:5px 10px;border-radius:14px;font-size:.7rem;cursor:pointer}.chip:hover{border-color:var(--blue);color:var(--blue)}
.lead-row{background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:14px;margin:6px 0;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
.lead-row .name{color:#fff;font-weight:600}.lead-row .detail{color:var(--muted);font-size:.7rem}
.badge{display:inline-block;padding:2px 8px;border-radius:6px;font-size:.6rem;font-weight:700}
.badge.hot{background:#22c55e20;color:#22c55e}.badge.warm{background:#f59e0b20;color:#f59e0b}.badge.cold{background:#ef444420;color:#ef4444}
.overdue-row{border-left:3px solid var(--danger)}.today-row{border-left:3px solid var(--blue)}
.empty{text-align:center;color:var(--muted);padding:30px}
.modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.85);z-index:99;align-items:center;justify-content:center}
.modal.active{display:flex}.modal-content{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:28px;max-width:420px;width:90%;text-align:center}
</style></head><body>
<div class='container'>
<div class='topbar'><h1><span>Follow-Up</span> OS</h1>
<div><span id='userEmail' style='color:var(--muted);font-size:.75rem'></span><a href='/api/logout' class='logout' id='logoutLink' style='display:none'>Logout</a></div></div>
<div id='saveBanner' class='save-banner' style='display:none'><span>⚠️ Your leads will be lost.</span><input type='email' id='bannerEmail' placeholder='Email'><input type='password' id='bannerPassword' placeholder='Password'><button class='btn' onclick='saveAccount()'>Save</button></div>
<div class='summary' id='summary'></div>
<div class='tabs'><div class='tab active' onclick='switchTab(\"add\")'>➕ Add</div><div class='tab' onclick='switchTab(\"today\")'>🔥 Today</div><div class='tab' onclick='switchTab(\"active\")'>📊 Active</div><div class='tab' onclick='switchTab(\"lost\")'>📁 Closed</div></div>
<div id='add' class='panel active'><div class='card'><h3>New Lead</h3><div class='quick-chips'><button class='chip' onclick='setSource(\"WhatsApp\")'>WhatsApp</button><button class='chip' onclick='setSource(\"Instagram\")'>Instagram</button><button class='chip' onclick='setSource(\"Facebook\")'>Facebook</button><button class='chip' onclick='setSource(\"Email\")'>Email</button><button class='chip' onclick='setSource(\"Phone\")'>Phone</button><button class='chip' onclick='setSource(\"Other\")'>Other</button></div><label>Name *</label><input id='l_name'><label>Source</label><input id='l_source'><label>Note</label><input id='l_note'><label>Value (₦)</label><input id='l_value' type='number'><label>Status</label><select id='l_status'><option value='hot'>Hot</option><option value='warm' selected>Warm</option><option value='cold'>Cold</option></select><label>Follow-up Date</label><input id='l_date' type='date'><button class='btn' onclick='addLead()' style='width:100%'>Save Lead</button></div></div>
<div id='today' class='panel'><div class='card'><h3>Today</h3><div id='todayList'></div></div></div>
<div id='active' class='panel'><div class='card'><h3>Active</h3><div id='activeList'></div></div></div>
<div id='lost' class='panel'><div class='card'><h3>Closed</h3><div id='lostList'></div></div></div></div>
<script>
var current='add',isLoggedIn=false;
fetch('/api/me').then(r=>r.json()).then(function(d){if(d.email){isLoggedIn=true;document.getElementById('userEmail').textContent=d.email;document.getElementById('logoutLink').style.display='inline';document.getElementById('saveBanner').style.display='none'}else{document.getElementById('saveBanner').style.display='flex'}loadSummary()});
function switchTab(t){current=t;document.querySelectorAll('.tab').forEach(function(x){x.classList.remove('active')});document.querySelectorAll('.panel').forEach(function(x){x.classList.remove('active')});document.getElementById(t).classList.add('active');if(t==='today')loadToday();if(t==='active')loadActive();if(t==='lost')loadLost();loadSummary()}
function loadSummary(){fetch('/api/summary').then(r=>r.json()).then(function(d){document.getElementById('summary').innerHTML='<div class=\"summary-card\"><div class=\"num\" style=\"color:var(--blue)\">'+d.today+'</div><div class=\"lbl\">Due Today</div></div><div class=\"summary-card\"><div class=\"num\" style=\"color:var(--danger)\">'+d.overdue+'</div><div class=\"lbl\">Overdue</div></div><div class=\"summary-card\"><div class=\"num\" style=\"color:var(--success)\">'+d.active+'</div><div class=\"lbl\">Active</div></div>'})}
function renderLeads(leads,container){var h='';if(!leads.length)h='<div class=\"empty\">Nothing here.</div>';leads.forEach(function(l){var cls=l.follow_up_date<new Date().toISOString().split('T')[0]?'overdue-row':(l.follow_up_date===new Date().toISOString().split('T')[0]?'today-row':'');h+='<div class=\"lead-row '+cls+'\"><div><div class=\"name\">'+l.name+' <span class=\"badge '+l.status+'\">'+l.status.toUpperCase()+'</span></div><div class=\"detail\">'+(l.deal_value||0).toLocaleString()+' | '+l.follow_up_date+' | '+l.note+'</div></div><div style=\"display:flex;gap:4px\">';if(l.status!=='lost'&&l.status!=='closed'){h+='<button class=\"btn-sm btn-success\" onclick=\"updateStatus('+l.id+',&quot;closed&quot;)\">Won</button>';h+='<button class=\"btn-sm btn-danger\" onclick=\"updateStatus('+l.id+',&quot;lost&quot;)\">Lost</button>';h+='<button class=\"btn-sm btn-warn\" onclick=\"followedUp('+l.id+')\">Done</button>'}h+='</div></div>'});document.getElementById(container).innerHTML=h}
function loadToday(){fetch('/api/leads/today').then(r=>r.json()).then(function(d){renderLeads(d,'todayList')})}
function loadActive(){fetch('/api/leads/active').then(r=>r.json()).then(function(d){renderLeads(d,'activeList')})}
function loadLost(){fetch('/api/leads/lost').then(r=>r.json()).then(function(d){renderLeads(d,'lostList')})}
function setSource(s){document.getElementById('l_source').value=s}
async function saveAccount(){var e=document.getElementById('bannerEmail').value,p=document.getElementById('bannerPassword').value;if(!e||p.length<6)return;var r=await fetch('/api/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:e,password:p})});if(r.ok)location.reload()}
async function addLead(){var btn=document.querySelector('#add .btn'),orig=btn.innerHTML;btn.disabled=true;btn.innerHTML='Saving...';await fetch('/api/leads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:document.getElementById('l_name').value,source:document.getElementById('l_source').value,note:document.getElementById('l_note').value,deal_value:document.getElementById('l_value').value,status:document.getElementById('l_status').value,follow_up_date:document.getElementById('l_date').value})});document.getElementById('l_name').value='';document.getElementById('l_note').value='';document.getElementById('l_value').value='';btn.disabled=false;btn.innerHTML=orig;loadSummary();if(!isLoggedIn)document.getElementById('saveBanner').style.display='flex'}
async function updateStatus(id,s){await fetch('/api/leads/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:s})});if(current==='today')loadToday();else if(current==='active')loadActive();else loadLost();loadSummary()}
async function followedUp(id){var d=new Date();d.setDate(d.getDate()+3);await fetch('/api/leads/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({follow_up_date:d.toISOString().split('T')[0]})});if(current==='today')loadToday();else loadActive();loadSummary()}
document.getElementById('l_date').value=new Date().toISOString().split('T')[0];
loadSummary();
</script></body></html>"""

LOGIN_HTML = """<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1.0'><title>Login</title><style>:root{--bg:#06060e;--surface:#0c0c1a;--border:#1a1a35;--blue:#3b82f6}*{margin:0;padding:0}body{font-family:system-ui;background:var(--bg);color:#fff;min-height:100vh;display:flex;align-items:center;justify-content:center}.card{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:36px;width:100%;max-width:380px;text-align:center}h1{font-size:1.5rem;margin-bottom:4px}h1 span{color:var(--blue)}p{color:#7a7a90;font-size:.85rem;margin-bottom:24px}input{width:100%;background:var(--bg);border:1px solid var(--border);color:#fff;padding:12px;border-radius:10px;font-size:.9rem;margin-bottom:12px;outline:none}input:focus{border-color:var(--blue)}.btn{background:var(--blue);color:#fff;border:none;padding:13px;border-radius:10px;font-weight:700;cursor:pointer;width:100%}.error{color:#ef4444;font-size:.8rem;margin-bottom:12px}a{color:#7a7a90;font-size:.8rem;text-decoration:none;display:block;margin-top:12px}</style></head><body><div class='card'><h1><span>Follow-Up</span> OS</h1><p>Login to see your leads</p><div id='error' class='error'></div><form onsubmit='login(event)'><input type='email' id='email' placeholder='Email' required><input type='password' id='password' placeholder='Password' required><button class='btn'>Login</button></form><a href='/signup'>Create account</a></div><script>async function login(e){e.preventDefault();var r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:document.getElementById('email').value,password:document.getElementById('password').value})});if(r.ok)location.href='/app';else{var d=await r.json();document.getElementById('error').textContent=d.error}}</script></body></html>"""

SIGNUP_HTML = """<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1.0'><title>Sign Up</title><style>:root{--bg:#06060e;--surface:#0c0c1a;--border:#1a1a35;--blue:#3b82f6}*{margin:0;padding:0}body{font-family:system-ui;background:var(--bg);color:#fff;min-height:100vh;display:flex;align-items:center;justify-content:center}.card{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:36px;width:100%;max-width:380px;text-align:center}h1{font-size:1.5rem}h1 span{color:var(--blue)}p{color:#7a7a90;font-size:.85rem;margin-bottom:24px}input{width:100%;background:var(--bg);border:1px solid var(--border);color:#fff;padding:12px;border-radius:10px;font-size:.9rem;margin-bottom:12px;outline:none}input:focus{border-color:var(--blue)}.btn{background:var(--blue);color:#fff;border:none;padding:13px;border-radius:10px;font-weight:700;cursor:pointer;width:100%}.error{color:#ef4444;font-size:.8rem;margin-bottom:12px}a{color:#7a7a90;font-size:.8rem;text-decoration:none;display:block;margin-top:12px}</style></head><body><div class='card'><h1><span>Follow-Up</span> OS</h1><p>Create your free account</p><div id='error' class='error'></div><form onsubmit='signup(event)'><input type='email' id='email' placeholder='Email' required><input type='password' id='password' placeholder='Password (6+ chars)' minlength='6' required><button class='btn'>Create Account</button></form><a href='/login'>Already have an account?</a></div><script>async function signup(e){e.preventDefault();var r=await fetch('/api/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:document.getElementById('email').value,password:document.getElementById('password').value})});if(r.ok)location.href='/app';else{var d=await r.json();document.getElementById('error').textContent=d.error}}</script></body></html>"""

@app.get("/")
@app.get("/app")
async def main_page():
    return HTMLResponse(HTML_PAGE)

@app.get("/login")
async def login_page(request: Request):
    if fetch_user(request): return RedirectResponse("/app")
    return HTMLResponse(LOGIN_HTML)

@app.get("/signup")
async def signup_page():
    return HTMLResponse(SIGNUP_HTML)

@app.get("/api/me")
async def me(request: Request):
    user = fetch_user(request)
    if not user: return JSONResponse({"email": None})
    return {"id": user["id"], "email": user["email"], "streak": user.get("streak",0)}

@app.post("/api/signup")
async def signup(request: Request):
    data = await request.json()
    email = data.get("email","").strip().lower()
    password = data.get("password","").strip()
    if not email or len(password) < 6: return JSONResponse({"error": "Email and 6+ char password required"}, status_code=400)
    try:
        token = str(uuid.uuid4())
        execute_query("INSERT INTO users (email,password,token,created,last_login) VALUES (%s,%s,%s,%s,%s)", (email, hash_pw(password), token, datetime.now().isoformat(), datetime.now().isoformat()))
        execute_query("UPDATE leads SET user_id=(SELECT id FROM users WHERE token=%s) WHERE user_id=0 AND session_id=%s", (token, request.cookies.get("session_id","")))
        resp = JSONResponse({"ok": True})
        resp.set_cookie("token", token, httponly=True, max_age=86400*365)
        return resp
    except: return JSONResponse({"error": "Email already registered"}, status_code=400)

@app.post("/api/login")
async def login(request: Request):
    data = await request.json()
    email = data.get("email","").strip().lower()
    password = data.get("password","").strip()
    rows = execute_query("SELECT * FROM users WHERE email=%s", (email,))
    if not rows or not check_pw(password, rows[0]["password"]): return JSONResponse({"error": "Invalid email or password"}, status_code=401)
    token = str(uuid.uuid4())
    execute_query("UPDATE users SET token=%s, last_login=%s WHERE id=%s", (token, datetime.now().isoformat(), rows[0]["id"]))
    resp = JSONResponse({"ok": True})
    resp.set_cookie("token", token, httponly=True, max_age=86400*365)
    return resp

@app.get("/api/logout")
async def logout():
    resp = RedirectResponse("/"); resp.delete_cookie("token"); return resp

@app.get("/api/summary")
async def summary(request: Request):
    user = fetch_user(request); uid = user["id"] if user else 0
    return {"today": len(today_leads(uid)), "overdue": len(overdue_leads(uid)), "active": len(active_leads(uid))}

@app.post("/api/leads")
async def add_lead(request: Request):
    user = fetch_user(request); uid = user["id"] if user else 0
    sid = request.cookies.get("session_id", "0")
    data = await request.json(); now = datetime.now().isoformat()
    execute_query("INSERT INTO leads (user_id,session_id,name,source,note,deal_value,status,follow_up_date,created,updated) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (uid, sid, data.get("name",""), data.get("source",""), data.get("note",""), data.get("deal_value",0), data.get("status","warm"), data.get("follow_up_date",date.today().isoformat()), now, now))
    return {"ok": True}

@app.get("/api/leads/today")
async def today(request: Request):
    user = fetch_user(request); return today_leads(user["id"] if user else 0)

@app.get("/api/leads/active")
async def active(request: Request):
    user = fetch_user(request); return active_leads(user["id"] if user else 0)

@app.get("/api/leads/lost")
async def lost(request: Request):
    user = fetch_user(request); return closed_leads(user["id"] if user else 0)

@app.put("/api/leads/{lead_id}")
async def update_lead(lead_id: int, request: Request):
    user = fetch_user(request); uid = user["id"] if user else 0
    data = await request.json(); now = datetime.now().isoformat()
    for key in ["status","follow_up_date","last_contacted"]:
        if key in data: execute_query(f"UPDATE leads SET {key}=%s, updated=%s WHERE id=%s AND user_id=%s", (data[key], now, lead_id, uid))
    if data.get("status") == "closed" and uid > 0:
        today_str = date.today().isoformat()
        rows = execute_query("SELECT streak, last_streak_date FROM users WHERE id=%s", (uid,))
        if rows:
            r = rows[0]; last = r["last_streak_date"]
            if last == today_str: pass
            elif last and (date.today() - date.fromisoformat(last)).days == 1: execute_query("UPDATE users SET streak=streak+1, last_streak_date=%s WHERE id=%s", (today_str, uid))
            else: execute_query("UPDATE users SET streak=1, last_streak_date=%s WHERE id=%s", (today_str, uid))
    return {"ok": True}

@app.get("/dashboard")
async def dashboard_page(request: Request):
    if request.cookies.get("admin_token") != ADMIN_PASS:
        return HTMLResponse('<html><body style="background:#06060e;color:#fff;font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh"><form method="post" action="/dashboard/login"><input name="password" type="password" placeholder="Admin password" style="padding:14px;background:#0c0c1a;border:1px solid #1a1a35;color:#fff;border-radius:14px"><button style="padding:14px 24px;background:#3b82f6;color:#fff;border:none;border-radius:14px;cursor:pointer;font-weight:600;margin-top:8px">Access</button></form></body></html>')
    rows = execute_query("SELECT id, email, created, last_login, streak FROM users ORDER BY last_login DESC")
    html = '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Dashboard</title><style>body{font-family:system-ui;background:#06060e;color:#d4d4d8;padding:40px}h1{color:#3b82f6}table{width:100%;border-collapse:collapse}th,td{padding:14px;text-align:left;border-bottom:1px solid #1a1a35}th{color:#3b82f6}</style></head><body><h1>Dashboard</h1><table><tr><th>Email</th><th>Leads</th><th>Signed Up</th><th>Last Login</th></tr>'
    for u in (rows or []):
        cnt = execute_query("SELECT COUNT(*) FROM leads WHERE user_id=%s", (u["id"],))[0]["count"]
        html += f"<tr><td>{u['email']}</td><td>{cnt}</td><td>{u['created'][:10] if u['created'] else '-'}</td><td>{u['last_login'][:16] if u['last_login'] else 'Never'}</td></tr>"
    html += "</table></body></html>"
    return HTMLResponse(html)

@app.post("/dashboard/login")
async def dashboard_login(request: Request):
    data = await request.form()
    if data.get("password") == ADMIN_PASS:
        resp = RedirectResponse("/dashboard", status_code=303)
        resp.set_cookie("admin_token", ADMIN_PASS, httponly=True)
        return resp
    return RedirectResponse("/dashboard")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
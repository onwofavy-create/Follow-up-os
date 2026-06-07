from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import json, sqlite3, uuid, bcrypt, os
from datetime import datetime, date, timedelta
from pathlib import Path

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DB = Path("followup.db")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "followup2024")

@app.middleware("http")
async def session_middleware(request: Request, call_next):
    response = await call_next(request)
    if not request.cookies.get("session_id") and not request.cookies.get("token"):
        response.set_cookie("session_id", str(uuid.uuid4()), httponly=True, max_age=86400*365)
    return response

def init_db():
    conn = sqlite3.connect(str(DB))
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, token TEXT, created TEXT, last_login TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS leads (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL DEFAULT 0, session_id TEXT DEFAULT '0', name TEXT NOT NULL, source TEXT, note TEXT, deal_value INTEGER DEFAULT 0, status TEXT DEFAULT 'warm', follow_up_date TEXT, last_contacted TEXT, created TEXT, updated TEXT)")
    conn.commit()
    return conn

init_db()

def hash_pw(password): return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
def check_pw(password, hashed): return bcrypt.checkpw(password.encode(), hashed.encode())

def fetch_user(request: Request):
    token = request.cookies.get("token")
    if not token: return None
    conn = sqlite3.connect(str(DB)); conn.row_factory = sqlite3.Row
    user = conn.execute("SELECT * FROM users WHERE token=?", (token,)).fetchone()
    conn.close()
    return dict(user) if user else None

def run_query(query, params=()):
    conn = sqlite3.connect(str(DB)); conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(query, params)
    if query.strip().upper().startswith("SELECT"):
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        conn.close()
        return [dict(zip(cols, r)) for r in rows]
    conn.commit(); conn.close()
    return []

def get_leads_query(user_id, session_id, status_filter):
    today = date.today().isoformat()
    if user_id > 0:
        if status_filter == "today":
            return run_query("SELECT * FROM leads WHERE user_id=? AND follow_up_date <= ? AND status NOT IN ('lost','closed') ORDER BY follow_up_date ASC", (user_id, today))
        elif status_filter == "overdue":
            return run_query("SELECT * FROM leads WHERE user_id=? AND follow_up_date < ? AND status NOT IN ('lost','closed') ORDER BY follow_up_date ASC", (user_id, today))
        elif status_filter == "active":
            return run_query("SELECT * FROM leads WHERE user_id=? AND status NOT IN ('lost','closed') ORDER BY follow_up_date ASC", (user_id,))
        else:
            return run_query("SELECT * FROM leads WHERE user_id=? AND status IN ('lost','closed') ORDER BY updated DESC LIMIT 30", (user_id,))
    else:
        if status_filter == "today":
            return run_query("SELECT * FROM leads WHERE user_id=0 AND session_id=? AND follow_up_date <= ? AND status NOT IN ('lost','closed') ORDER BY follow_up_date ASC", (session_id, today))
        elif status_filter == "overdue":
            return run_query("SELECT * FROM leads WHERE user_id=0 AND session_id=? AND follow_up_date < ? AND status NOT IN ('lost','closed') ORDER BY follow_up_date ASC", (session_id, today))
        elif status_filter == "active":
            return run_query("SELECT * FROM leads WHERE user_id=0 AND session_id=? AND status NOT IN ('lost','closed') ORDER BY follow_up_date ASC", (session_id,))
        else:
            return run_query("SELECT * FROM leads WHERE user_id=0 AND session_id=? AND status IN ('lost','closed') ORDER BY updated DESC LIMIT 30", (session_id,))

HTML = """
<!DOCTYPE html>
<html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1.0'><title>Follow-Up OS</title>
<style>:root{--bg:#06060e;--surface:#0c0c1a;--border:#1a1a35;--text:#e0e0e8;--muted:#7a7a90;--blue:#3b82f6;--orange:#ff6b35;--success:#22c55e;--warn:#f59e0b;--danger:#ef4444}*{margin:0;padding:0;box-sizing:border-box}body{font-family:system-ui;background:var(--bg);color:var(--text);min-height:100vh;padding:20px}.container{max-width:900px;margin:0 auto}.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}.topbar h1{font-size:1.3rem;color:#fff}.topbar h1 span{color:var(--blue)}.logout{color:var(--muted);text-decoration:none;font-size:.8rem}.save-banner{background:var(--surface);border:1px solid var(--warn);border-radius:12px;padding:14px;margin-bottom:20px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;justify-content:center}.save-banner span{color:var(--warn);font-weight:600;font-size:.8rem}.save-banner input{background:var(--bg);border:1px solid var(--border);color:#fff;padding:8px 12px;border-radius:8px;font-size:.8rem}.btn{background:var(--blue);color:#fff;border:none;padding:10px 18px;border-radius:8px;font-weight:600;cursor:pointer;font-size:.8rem}.btn-orange{background:var(--orange)}.btn-success{background:var(--success)}.btn-danger{background:var(--danger)}.btn-warn{background:var(--warn);color:#000}.btn-sm{padding:6px 12px;font-size:.7rem;border-radius:6px;border:none;cursor:pointer;font-weight:600}.summary{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap}.summary-card{flex:1;min-width:120px;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:18px;text-align:center}.summary-card .num{font-size:2rem;font-weight:800}.summary-card .lbl{color:var(--muted);font-size:.65rem;text-transform:uppercase}.tabs{display:flex;gap:4px;margin-bottom:20px}.tab{flex:1;text-align:center;padding:10px;border-radius:8px;cursor:pointer;background:var(--surface);border:1px solid var(--border);color:var(--muted);font-weight:600;font-size:.75rem}.tab.active{background:var(--blue);color:#fff}.panel{display:none}.panel.active{display:block}.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:16px}.card h3{color:var(--muted);font-size:.7rem;text-transform:uppercase;margin-bottom:14px}input,textarea,select{width:100%;background:var(--bg);border:1px solid var(--border);color:#fff;padding:10px;border-radius:8px;margin-bottom:10px;font-size:.85rem;font-family:inherit;outline:none}label{display:block;color:var(--muted);font-size:.65rem;text-transform:uppercase;margin-bottom:3px}.quick-chips{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:12px}.chip{background:var(--surface);border:1px solid var(--border);color:var(--muted);padding:5px 10px;border-radius:14px;font-size:.7rem;cursor:pointer}.chip:hover{border-color:var(--blue);color:var(--blue)}.lead-row{background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:14px;margin:6px 0;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}.lead-row .name{color:#fff;font-weight:600}.lead-row .detail{color:var(--muted);font-size:.7rem}.badge{display:inline-block;padding:2px 8px;border-radius:6px;font-size:.6rem;font-weight:700}.badge.hot{background:#22c55e20;color:#22c55e}.badge.warm{background:#f59e0b20;color:#f59e0b}.badge.cold{background:#ef444420;color:#ef4444}.overdue-row{border-left:3px solid var(--danger)}.today-row{border-left:3px solid var(--blue)}.empty{text-align:center;color:var(--muted);padding:30px}</style></head><body>
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

@app.get("/")
@app.get("/app")
async def main_page(): return HTMLResponse(HTML)

@app.get("/api/me")
async def me(request: Request):
    user = fetch_user(request)
    if not user: return JSONResponse({"email": None})
    return {"id": user["id"], "email": user["email"]}

@app.post("/api/signup")
async def signup(request: Request):
    data = await request.json()
    email = data.get("email","").strip().lower()
    password = data.get("password","").strip()
    if not email or len(password) < 6: return JSONResponse({"error": "Email and 6+ char password required"}, status_code=400)
    conn = sqlite3.connect(str(DB))
    try:
        token = str(uuid.uuid4())
        conn.execute("INSERT INTO users (email,password,token,created,last_login) VALUES (?,?,?,?,?)", (email, hash_pw(password), token, datetime.now().isoformat(), datetime.now().isoformat()))
        conn.execute("UPDATE leads SET user_id=(SELECT id FROM users WHERE token=?) WHERE user_id=0 AND session_id=?", (token, request.cookies.get("session_id","")))
        conn.commit()
        resp = JSONResponse({"ok": True})
        resp.set_cookie("token", token, httponly=True, max_age=86400*365)
        return resp
    except sqlite3.IntegrityError:
        return JSONResponse({"error": "Email already registered"}, status_code=400)
    finally: conn.close()

@app.post("/api/login")
async def login(request: Request):
    data = await request.json()
    email = data.get("email","").strip().lower()
    password = data.get("password","").strip()
    conn = sqlite3.connect(str(DB)); conn.row_factory = sqlite3.Row
    user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not user or not check_pw(password, user["password"]):
        conn.close(); return JSONResponse({"error": "Invalid email or password"}, status_code=401)
    token = str(uuid.uuid4())
    conn.execute("UPDATE users SET token=?, last_login=? WHERE id=?", (token, datetime.now().isoformat(), user["id"]))
    conn.commit(); conn.close()
    resp = JSONResponse({"ok": True})
    resp.set_cookie("token", token, httponly=True, max_age=86400*365)
    return resp

@app.get("/api/logout")
async def logout():
    resp = RedirectResponse("/"); resp.delete_cookie("token"); return resp

@app.get("/api/summary")
async def summary(request: Request):
    user = fetch_user(request)
    uid = user["id"] if user else 0
    sid = request.cookies.get("session_id","0")
    return {"today": len(get_leads_query(uid, sid, "today")), "overdue": len(get_leads_query(uid, sid, "overdue")), "active": len(get_leads_query(uid, sid, "active"))}

@app.post("/api/leads")
async def add_lead(request: Request):
    user = fetch_user(request)
    uid = user["id"] if user else 0
    sid = request.cookies.get("session_id", str(uuid.uuid4()))
    data = await request.json()
    now = datetime.now().isoformat()
    conn = sqlite3.connect(str(DB))
    conn.execute("INSERT INTO leads (user_id,session_id,name,source,note,deal_value,status,follow_up_date,created,updated) VALUES (?,?,?,?,?,?,?,?,?,?)", (uid, sid, data.get("name",""), data.get("source",""), data.get("note",""), data.get("deal_value",0), data.get("status","warm"), data.get("follow_up_date",date.today().isoformat()), now, now))
    conn.commit(); conn.close()
    resp = JSONResponse({"ok": True})
    if not request.cookies.get("session_id"):
        resp.set_cookie("session_id", sid, httponly=True, max_age=86400*365)
    return resp

@app.get("/api/leads/today")
async def today(request: Request):
    user = fetch_user(request)
    return get_leads_query(user["id"] if user else 0, request.cookies.get("session_id","0"), "today")

@app.get("/api/leads/active")
async def active(request: Request):
    user = fetch_user(request)
    return get_leads_query(user["id"] if user else 0, request.cookies.get("session_id","0"), "active")

@app.get("/api/leads/lost")
async def lost(request: Request):
    user = fetch_user(request)
    return get_leads_query(user["id"] if user else 0, request.cookies.get("session_id","0"), "closed")

@app.put("/api/leads/{lead_id}")
async def update_lead(lead_id: int, request: Request):
    user = fetch_user(request)
    uid = user["id"] if user else 0
    sid = request.cookies.get("session_id","0")
    data = await request.json()
    now = datetime.now().isoformat()
    conn = sqlite3.connect(str(DB))
    if uid > 0:
        conn.execute(f"UPDATE leads SET status=?, updated=? WHERE id=? AND user_id=?", (data.get("status","warm"), now, lead_id, uid))
    else:
        conn.execute(f"UPDATE leads SET status=?, updated=? WHERE id=? AND session_id=?", (data.get("status","warm"), now, lead_id, sid))
    if "follow_up_date" in data:
        if uid > 0:
            conn.execute("UPDATE leads SET follow_up_date=?, updated=? WHERE id=? AND user_id=?", (data["follow_up_date"], now, lead_id, uid))
        else:
            conn.execute("UPDATE leads SET follow_up_date=?, updated=? WHERE id=? AND session_id=?", (data["follow_up_date"], now, lead_id, sid))
    conn.commit(); conn.close()
    return {"ok": True}

@app.get("/dashboard")
async def dashboard_page(request: Request):
    if request.cookies.get("admin_token") != ADMIN_PASS:
        return HTMLResponse('<html><body style="background:#06060e;color:#fff;font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh"><form method="post" action="/dashboard/login"><input name="password" type="password" placeholder="Admin password" style="padding:14px;background:#0c0c1a;border:1px solid #1a1a35;color:#fff;border-radius:14px"><button style="padding:14px 24px;background:#3b82f6;color:#fff;border:none;border-radius:14px;cursor:pointer;font-weight:600;margin-top:8px">Access</button></form></body></html>')
    rows = run_query("SELECT id, email, created, last_login FROM users ORDER BY last_login DESC")
    html = '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Dashboard</title><style>body{font-family:system-ui;background:#06060e;color:#d4d4d8;padding:40px}h1{color:#3b82f6}table{width:100%;border-collapse:collapse}th,td{padding:14px;text-align:left;border-bottom:1px solid #1a1a35}th{color:#3b82f6}</style></head><body><h1>Dashboard</h1><table><tr><th>Email</th><th>Leads</th><th>Signed Up</th><th>Last Login</th></tr>'
    for u in (rows or []):
        cnt = run_query("SELECT COUNT(*) FROM leads WHERE user_id=?", (u["id"],))[0]["count"]
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
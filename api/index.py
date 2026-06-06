from fastapi import FastAPI, Request, Response, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import json, os, io, uuid, bcrypt, psycopg2, re
from datetime import datetime, date, timedelta

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DATABASE_URL = os.environ.get("DATABASE_URL", "")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "followup2024")

def get_db():
    return psycopg2.connect(DATABASE_URL) if DATABASE_URL else None

def init_db():
    if not DATABASE_URL: return
    conn = get_db(); cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, token TEXT, streak INTEGER DEFAULT 0, last_streak_date TEXT, created TEXT, last_login TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS leads (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL DEFAULT 0, session_id TEXT DEFAULT '0', name TEXT NOT NULL, source TEXT, note TEXT, deal_value INTEGER DEFAULT 0, status TEXT DEFAULT 'warm', follow_up_date TEXT, last_contacted TEXT, nudge_enabled INTEGER DEFAULT 0, created TEXT, updated TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS history (id SERIAL PRIMARY KEY, lead_id INTEGER, user_id INTEGER, action TEXT, note TEXT, created TEXT)")
    conn.commit(); conn.close()

init_db()

def hash_password(password): return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
def check_password(password, hashed): return bcrypt.checkpw(password.encode(), hashed.encode())

def get_user(request: Request):
    token = request.cookies.get("token")
    if not token or not DATABASE_URL: return None
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE token=%s", (token,))
    row = cur.fetchone()
    conn.close()
    if row: return dict(zip(["id","email","password","token","streak","last_streak_date","created","last_login"], row))
    return None

def run_query(query, params=()):
    if not DATABASE_URL: return []
    conn = get_db(); cur = conn.cursor()
    cur.execute(query, params)
    if query.strip().upper().startswith("SELECT"):
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        conn.close()
        return [dict(zip(cols, r)) for r in rows]
    conn.commit(); conn.close()
    return []

def get_today_leads(user_id):
    today = date.today().isoformat()
    return run_query("SELECT * FROM leads WHERE user_id=%s AND follow_up_date <= %s AND status NOT IN ('lost','closed') ORDER BY follow_up_date ASC", (user_id, today))

def get_overdue_leads(user_id):
    today = date.today().isoformat()
    return run_query("SELECT * FROM leads WHERE user_id=%s AND follow_up_date < %s AND status NOT IN ('lost','closed') ORDER BY follow_up_date ASC", (user_id, today))

def get_active_leads(user_id):
    return run_query("SELECT * FROM leads WHERE user_id=%s AND status NOT IN ('lost','closed') ORDER BY follow_up_date ASC", (user_id,))

def get_lost_leads(user_id):
    return run_query("SELECT * FROM leads WHERE user_id=%s AND status IN ('lost','closed') ORDER BY updated DESC LIMIT 30", (user_id,))

# ── ROUTES ──

@app.get("/")
async def home(): return RedirectResponse("/app")

@app.get("/app", response_class=HTMLResponse)
async def app_page(request: Request):
    html = open("app.html", "r", encoding="utf-8").read()
    return html

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_user(request): return RedirectResponse("/app")
    return """<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1.0'><title>Login</title><style>:root{--bg:#06060e;--surface:#0c0c1a;--border:#1a1a35;--blue:#3b82f6}*{margin:0;padding:0}body{font-family:system-ui;background:var(--bg);color:#fff;min-height:100vh;display:flex;align-items:center;justify-content:center}.card{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:36px;width:100%;max-width:380px;text-align:center}h1{font-size:1.5rem;margin-bottom:4px}h1 span{color:var(--blue)}p{color:#7a7a90;font-size:.85rem;margin-bottom:24px}input{width:100%;background:var(--bg);border:1px solid var(--border);color:#fff;padding:12px;border-radius:10px;font-size:.9rem;margin-bottom:12px;outline:none}input:focus{border-color:var(--blue)}.btn{background:var(--blue);color:#fff;border:none;padding:13px;border-radius:10px;font-weight:700;cursor:pointer;width:100%}.error{color:#ef4444;font-size:.8rem;margin-bottom:12px}a{color:#7a7a90;font-size:.8rem;text-decoration:none;display:block;margin-top:12px}</style></head><body><div class='card'><h1><span>Follow-Up</span> OS</h1><p>Login to see your leads</p><div id='error' class='error'></div><form onsubmit='login(event)'><input type='email' id='email' placeholder='Email' required><input type='password' id='password' placeholder='Password' required><button class='btn'>Login</button></form><a href='/signup'>Create account</a></div><script>async function login(e){e.preventDefault();var r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:document.getElementById('email').value,password:document.getElementById('password').value})});if(r.ok)location.href='/app';else{var d=await r.json();document.getElementById('error').textContent=d.error}}</script></body></html>"""

@app.get("/signup", response_class=HTMLResponse)
async def signup_page():
    return """<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1.0'><title>Sign Up</title><style>:root{--bg:#06060e;--surface:#0c0c1a;--border:#1a1a35;--blue:#3b82f6}*{margin:0;padding:0}body{font-family:system-ui;background:var(--bg);color:#fff;min-height:100vh;display:flex;align-items:center;justify-content:center}.card{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:36px;width:100%;max-width:380px;text-align:center}h1{font-size:1.5rem}h1 span{color:var(--blue)}p{color:#7a7a90;font-size:.85rem;margin-bottom:24px}input{width:100%;background:var(--bg);border:1px solid var(--border);color:#fff;padding:12px;border-radius:10px;font-size:.9rem;margin-bottom:12px;outline:none}input:focus{border-color:var(--blue)}.btn{background:var(--blue);color:#fff;border:none;padding:13px;border-radius:10px;font-weight:700;cursor:pointer;width:100%}.error{color:#ef4444;font-size:.8rem;margin-bottom:12px}a{color:#7a7a90;font-size:.8rem;text-decoration:none;display:block;margin-top:12px}</style></head><body><div class='card'><h1><span>Follow-Up</span> OS</h1><p>Create your free account</p><div id='error' class='error'></div><form onsubmit='signup(event)'><input type='email' id='email' placeholder='Email' required><input type='password' id='password' placeholder='Password (6+ chars)' minlength='6' required><button class='btn'>Create Account</button></form><a href='/login'>Already have an account?</a></div><script>async function signup(e){e.preventDefault();var r=await fetch('/api/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:document.getElementById('email').value,password:document.getElementById('password').value})});if(r.ok)location.href='/app';else{var d=await r.json();document.getElementById('error').textContent=d.error}}</script></body></html>"""

@app.get("/cost-of-silence", response_class=HTMLResponse)
async def cos_page():
    return """<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1.0'><title>Cost of Silence</title><style>:root{--bg:#06060e;--surface:#0c0c1a;--border:#1a1a35;--blue:#3b82f6;--danger:#ef4444}*{margin:0;padding:0}body{font-family:system-ui;background:var(--bg);color:#fff;min-height:100vh;display:flex;align-items:center;justify-content:center;text-align:center;padding:20px}.num{font-size:4rem;font-weight:800;color:var(--danger)}.lbl{color:#7a7a90;font-size:1rem;margin-bottom:24px}.stat{display:inline-block;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 24px;margin:8px}.stat .val{font-size:1.5rem;font-weight:700;color:var(--blue)}.stat .lbl{font-size:.65rem;color:#7a7a90;text-transform:uppercase}.btn{display:inline-block;background:var(--blue);color:#fff;text-decoration:none;padding:14px 32px;border-radius:10px;font-weight:700;margin-top:20px}</style></head><body><div><div class='num' id='total'>...</div><div class='lbl'>in unclosed deals dying in DMs right now.</div><div class='stat'><div class='val' id='daily'>...</div><div class='lbl'>Daily Loss</div></div><div class='stat'><div class='val' id='count'>...</div><div class='lbl'>Overdue</div></div><br><a href='/app' class='btn'>Stop Losing Money - Free</a></div><script>fetch('/api/public/cost-of-silence').then(r=>r.json()).then(d=>{document.getElementById('total').textContent='₦'+d.total_at_risk.toLocaleString();document.getElementById('daily').textContent='₦'+d.daily_loss_estimate.toLocaleString();document.getElementById('count').textContent=d.overdue_deals})</script></body></html>"""

@app.get("/resurrect", response_class=HTMLResponse)
async def resurrect_page():
    return """<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1.0'><title>Resurrect a Lead</title><style>:root{--bg:#06060e;--surface:#0c0c1a;--border:#1a1a35;--blue:#3b82f6}*{margin:0;padding:0}body{font-family:system-ui;background:var(--bg);color:#fff;min-height:100vh;padding:40px 20px}.container{max-width:600px;margin:0 auto}h1{text-align:center;font-size:1.8rem;margin-bottom:4px}h1 span{color:var(--blue)}p.sub{text-align:center;color:#7a7a90;margin-bottom:28px}label{display:block;color:#7a7a90;font-size:.65rem;text-transform:uppercase;margin-bottom:4px}input,textarea{width:100%;background:var(--surface);border:1px solid var(--border);color:#fff;padding:12px;border-radius:10px;font-size:.9rem;margin-bottom:14px;outline:none;font-family:inherit}input:focus,textarea:focus{border-color:var(--blue)}textarea{resize:vertical;min-height:80px}.btn{background:var(--blue);color:#fff;border:none;padding:14px;border-radius:10px;font-weight:700;cursor:pointer;width:100%}.result{background:var(--surface);border:1px solid #22c55e40;border-radius:12px;padding:20px;margin-top:16px;display:none}.result.active{display:block}.msg{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:14px;font-size:.85rem;line-height:1.6;margin:8px 0;white-space:pre-wrap}.copy-btn{background:#22c55e;color:#fff;border:none;padding:8px 16px;border-radius:8px;cursor:pointer;font-weight:600}.cta{margin-top:16px;text-align:center;color:#7a7a90;font-size:.8rem}.cta a{color:var(--blue)}</style></head><body><div class='container'><h1><span>Resurrect</span> a Dead Lead</h1><p class='sub'>Paste the conversation. Get the exact message to send.</p><label>Your Name</label><input id='r_name'><label>Their Name</label><input id='r_theirName'><label>Last Message</label><textarea id='r_lastMsg'></textarea><label>What was it about?</label><input id='r_context'><label>Days Since Contact</label><input id='r_days' type='number' value='7'><button class='btn' onclick='resurrect()'>Generate Message</button><div class='result' id='result'><p style='color:#22c55e;font-weight:700;margin-bottom:8px'>Your Message</p><div class='msg' id='genMsg'></div><button class='copy-btn' onclick='copyMsg()'>📋 Copy</button></div><div class='cta'>Want to never lose a lead again? <a href='/app'>Try Follow-Up OS free →</a></div></div><script>async function resurrect(){var btn=document.querySelector('.btn');var orig=btn.innerHTML;btn.disabled=true;btn.innerHTML='Generating...';var r=await fetch('/api/resurrect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:document.getElementById('r_name').value,theirName:document.getElementById('r_theirName').value,lastMsg:document.getElementById('r_lastMsg').value,context:document.getElementById('r_context').value,days:document.getElementById('r_days').value})});var d=await r.json();document.getElementById('genMsg').textContent=d.message;document.getElementById('result').classList.add('active');btn.disabled=false;btn.innerHTML=orig}function copyMsg(){navigator.clipboard.writeText(document.getElementById('genMsg').textContent);alert('Copied!')}</script></body></html>"""

# ── API ROUTES ──

@app.get("/api/public/cost-of-silence")
async def cost_of_silence():
    total = run_query("SELECT SUM(deal_value) FROM leads WHERE follow_up_date < CURRENT_DATE AND status NOT IN ('lost','closed')")
    count = run_query("SELECT COUNT(*) FROM leads WHERE follow_up_date < CURRENT_DATE AND status NOT IN ('lost','closed')")
    t = total[0]['sum'] if total and total[0]['sum'] else 0
    c = count[0]['count'] if count else 0
    return {"overdue_deals": c, "total_at_risk": int(t), "daily_loss_estimate": round(int(t)*0.02,2)}

@app.get("/api/me")
async def me(request: Request):
    user = get_user(request)
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
        run_query("INSERT INTO users (email,password,token,created,last_login) VALUES (%s,%s,%s,%s,%s)", (email, hash_password(password), token, datetime.now().isoformat(), datetime.now().isoformat()))
        run_query("UPDATE leads SET user_id=(SELECT id FROM users WHERE token=%s) WHERE user_id=0 AND session_id=%s", (token, request.cookies.get("session_id","")))
        resp = JSONResponse({"ok": True})
        resp.set_cookie("token", token, httponly=True, max_age=86400*365)
        return resp
    except: return JSONResponse({"error": "Email already registered"}, status_code=400)

@app.post("/api/login")
async def login(request: Request):
    data = await request.json()
    email = data.get("email","").strip().lower()
    password = data.get("password","").strip()
    rows = run_query("SELECT * FROM users WHERE email=%s", (email,))
    if not rows or not check_password(password, rows[0]["password"]): return JSONResponse({"error": "Invalid email or password"}, status_code=401)
    token = str(uuid.uuid4())
    run_query("UPDATE users SET token=%s, last_login=%s WHERE id=%s", (token, datetime.now().isoformat(), rows[0]["id"]))
    resp = JSONResponse({"ok": True})
    resp.set_cookie("token", token, httponly=True, max_age=86400*365)
    return resp

@app.get("/api/logout")
async def logout():
    resp = RedirectResponse("/login"); resp.delete_cookie("token"); return resp

@app.get("/api/summary")
async def summary(request: Request):
    user = get_user(request); uid = user["id"] if user else 0
    return {"today": len(get_today_leads(uid)), "overdue": len(get_overdue_leads(uid)), "active": len(get_active_leads(uid))}

@app.post("/api/leads")
async def add_lead(request: Request):
    user = get_user(request); uid = user["id"] if user else 0
    sid = request.cookies.get("session_id", "0")
    data = await request.json(); now = datetime.now().isoformat()
    run_query("INSERT INTO leads (user_id,session_id,name,source,note,deal_value,status,follow_up_date,created,updated) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (uid, sid, data.get("name",""), data.get("source",""), data.get("note",""), data.get("deal_value",0), data.get("status","warm"), data.get("follow_up_date",date.today().isoformat()), now, now))
    return {"ok": True}

@app.get("/api/leads/today")
async def today(request: Request):
    user = get_user(request); return get_today_leads(user["id"] if user else 0)

@app.get("/api/leads/active")
async def active(request: Request):
    user = get_user(request); return get_active_leads(user["id"] if user else 0)

@app.get("/api/leads/lost")
async def lost(request: Request):
    user = get_user(request); return get_lost_leads(user["id"] if user else 0)

@app.put("/api/leads/{lead_id}")
async def update_lead(lead_id: int, request: Request):
    user = get_user(request); uid = user["id"] if user else 0
    data = await request.json(); now = datetime.now().isoformat()
    for key in ["status","follow_up_date","last_contacted"]:
        if key in data: run_query(f"UPDATE leads SET {key}=%s, updated=%s WHERE id=%s AND user_id=%s", (data[key], now, lead_id, uid))
    run_query("INSERT INTO history (lead_id,user_id,action,note,created) VALUES (%s,%s,%s,%s,%s)", (lead_id, uid, data.get("status","updated"), data.get("note",""), now))
    if data.get("status") == "closed" and uid > 0:
        today_str = date.today().isoformat()
        rows = run_query("SELECT streak, last_streak_date FROM users WHERE id=%s", (uid,))
        if rows:
            r = rows[0]; last = r["last_streak_date"]
            if last == today_str: pass
            elif last and (date.today() - date.fromisoformat(last)).days == 1: run_query("UPDATE users SET streak=streak+1, last_streak_date=%s WHERE id=%s", (today_str, uid))
            else: run_query("UPDATE users SET streak=1, last_streak_date=%s WHERE id=%s", (today_str, uid))
    return {"ok": True}

@app.post("/api/leads/{lead_id}/nudge")
async def toggle_nudge(lead_id: int, request: Request):
    user = get_user(request); uid = user["id"] if user else 0
    rows = run_query("SELECT nudge_enabled FROM leads WHERE id=%s AND user_id=%s", (lead_id, uid))
    if rows: run_query("UPDATE leads SET nudge_enabled=%s WHERE id=%s AND user_id=%s", (0 if rows[0]["nudge_enabled"] else 1, lead_id, uid))
    return {"ok": True}

@app.get("/api/leads/{lead_id}/reminder")
async def reminder(lead_id: int, request: Request):
    user = get_user(request); uid = user["id"] if user else 0
    rows = run_query("SELECT * FROM leads WHERE id=%s AND user_id=%s", (lead_id, uid))
    if not rows: return JSONResponse({"error": "Not found"}, status_code=404)
    lead = rows[0]; now = datetime.now()
    ics = f"BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Follow-Up OS//EN\nBEGIN:VEVENT\nDTSTART:{now.strftime('%Y%m%dT%H%M%S')}\nDTEND:{(now+timedelta(hours=1)).strftime('%Y%m%dT%H%M%S')}\nSUMMARY:Follow up with {lead['name']}\nBEGIN:VALARM\nTRIGGER:-PT15M\nACTION:DISPLAY\nDESCRIPTION:Time to follow up with {lead['name']}\nEND:VALARM\nEND:VEVENT\nEND:VCALENDAR"
    return StreamingResponse(io.BytesIO(ics.encode()), media_type="text/calendar", headers={"Content-Disposition": f"attachment; filename=followup_{lead['name']}.ics"})

@app.post("/api/import/whatsapp")
async def import_whatsapp(file: UploadFile = File(...)):
    content = (await file.read()).decode("utf-8", errors="ignore")
    contacts = []
    for line in content.split("\n"):
        line = line.strip()
        if not line: continue
        match = re.match(r'(\d+/\d+/\d+,\s+\d+:\d+)\s+-\s+(.+?):\s+(.+)', line)
        if match:
            name = match.group(2).strip()
            msg = match.group(3).strip()
            if name and name not in ["You", "System"] and not name.startswith("+"):
                contacts.append({"name": name, "lastMessage": msg[:100]})
    seen = set(); unique = []
    for c in contacts:
        if c["name"] not in seen: seen.add(c["name"]); unique.append(c)
    return {"contacts": unique[:30]}

@app.post("/api/resurrect")
async def resurrect_api(request: Request):
    data = await request.json()
    name = data.get("name","").strip(); their_name = data.get("theirName","").strip()
    last_msg = data.get("lastMsg","").strip(); context = data.get("context","").strip()
    days = data.get("days","7")
    greeting = f"Hey {their_name}" if their_name else "Hey"
    ctx = f"I was reviewing our conversation about {context}" if context else "I was going through old messages"
    urgency = "I realize I should have followed up sooner" if int(days) > 5 else "I wanted to follow up"
    return {"message": f"{greeting},\n\n{urgency}. {ctx} and {last_msg[:80] if last_msg else 'our last chat'} came to mind.\n\nNo pressure at all — if you're still interested, I'd love to pick this back up. If things have changed, no worries either.\n\n{'- ' + name if name else '- [Your Name]'}"}

@app.get("/dashboard")
async def dashboard_page(request: Request):
    if request.cookies.get("admin_token") != ADMIN_PASS:
        return HTMLResponse('<html><body style="background:#06060e;color:#fff;font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh"><form method="post" action="/dashboard/login"><input name="password" type="password" placeholder="Admin password" style="padding:14px;background:#0c0c1a;border:1px solid #1a1a35;color:#fff;border-radius:14px"><button style="padding:14px 24px;background:#3b82f6;color:#fff;border:none;border-radius:14px;cursor:pointer;font-weight:600;margin-top:8px">Access</button></form></body></html>')
    rows = run_query("SELECT id, email, created, last_login, streak FROM users ORDER BY last_login DESC")
    html = '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Dashboard</title><style>body{font-family:system-ui;background:#06060e;color:#d4d4d8;padding:40px}h1{color:#3b82f6}table{width:100%;border-collapse:collapse}th,td{padding:14px;text-align:left;border-bottom:1px solid #1a1a35}th{color:#3b82f6}.num{color:#22c55e;font-weight:700}</style></head><body><h1>Dashboard</h1><table><tr><th>Email</th><th>Leads</th><th>Signed Up</th><th>Last Login</th><th>Streak</th></tr>'
    for u in (rows or []):
        cnt = run_query("SELECT COUNT(*) FROM leads WHERE user_id=%s", (u["id"],))[0]["count"]
        html += f"<tr><td>{u['email']}</td><td class='num'>{cnt}</td><td>{u['created'][:10] if u['created'] else '-'}</td><td>{u['last_login'][:16] if u['last_login'] else 'Never'}</td><td>{u.get('streak',0) or 0} days</td></tr>"
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
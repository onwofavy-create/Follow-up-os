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

LANDING_HTML = r"""<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1.0'><title>Follow-Up OS</title><style>:root{--bg:#06060e;--surface:#0c0c1a;--border:#1a1a35;--text:#e0e0e8;--muted:#7a7a90;--blue:#3b82f6;--blue-glow:#3b82f640;--orange:#ff6b35;--danger:#ef4444}*{margin:0;padding:0;box-sizing:border-box}body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}.section{padding:80px 24px;max-width:900px;margin:0 auto;text-align:center}.hero h1{font-size:clamp(2rem,5vw,3rem);font-weight:800;line-height:1.15;color:#fff;margin-bottom:20px}.hero span{background:linear-gradient(135deg,var(--blue),var(--orange));-webkit-background-clip:text;-webkit-text-fill-color:transparent}.hero p{color:var(--muted);font-size:1.1rem;max-width:600px;margin:0 auto 32px}.live-number{display:inline-block;background:var(--surface);border:1px solid var(--danger);border-radius:16px;padding:16px 28px;margin-bottom:36px}.live-number .big{font-size:2rem;font-weight:800;color:var(--danger)}.live-number .lbl{color:var(--muted);font-size:.75rem}.btn-group{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}.btn-primary{background:var(--blue);color:#fff;text-decoration:none;padding:16px 36px;border-radius:14px;font-weight:700;font-size:.95rem}.btn-primary:hover{box-shadow:0 8px 25px var(--blue-glow)}.btn-outline{background:transparent;color:#fff;text-decoration:none;padding:16px 36px;border-radius:14px;font-weight:700;font-size:.95rem;border:1px solid var(--border)}.btn-outline:hover{border-color:var(--blue)}.features{display:flex;gap:20px;margin-top:60px;flex-wrap:wrap;justify-content:center}.feature{flex:1;min-width:200px;max-width:280px;background:var(--surface);border:1px solid var(--border);border-radius:18px;padding:28px 24px;text-align:center}.feature .icon{font-size:2rem;margin-bottom:12px}.feature h3{color:#fff;font-size:.9rem;margin-bottom:8px}.feature p{color:var(--muted);font-size:.8rem}.footer{text-align:center;padding:40px;color:var(--muted);font-size:.7rem}@media(max-width:640px){.section{padding:40px 16px}}</style></head><body><div class='section hero'><h1>You're losing money in <span>unread DMs</span> right now.</h1><p>Every forgotten follow-up is a deal that dies. Follow-Up OS tracks your leads and tells you exactly who to contact today.</p><div class='live-number'><div class='big' id='heroNumber'>...</div><div class='lbl'>in overdue deals tracked on Follow-Up OS</div></div><div class='btn-group'><a href='/app' class='btn-primary'>Try It Free — No Signup</a><a href='/resurrect' class='btn-outline'>Resurrect a Dead Lead</a></div></div><div class='features'><div class='feature'><div class='icon'>📱</div><h3>Add Leads in Seconds</h3><p>From WhatsApp, Instagram, or anywhere.</p></div><div class='feature'><div class='icon'>🔥</div><h3>Daily Follow-Up List</h3><p>See who needs a message today. Overdue highlighted.</p></div><div class='feature'><div class='icon'>📊</div><h3>Track Your Pipeline</h3><p>Active deals, closed wins, lost opportunities.</p></div></div><div class='footer'>No signup required. Start tracking immediately.</div><script>fetch('/api/public/cost-of-silence').then(r=>r.json()).then(d=>{document.getElementById('heroNumber').textContent='₦'+d.total_at_risk.toLocaleString()})</script></body></html>"""

RESURRECT_HTML = r"""<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1.0'><title>Resurrect a Dead Lead</title><style>:root{--bg:#06060e;--surface:#0c0c1a;--border:#1a1a35;--text:#e0e0e8;--muted:#7a7a90;--blue:#3b82f6;--blue-glow:#3b82f640;--orange:#ff6b35}*{margin:0;padding:0}body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;padding:40px 20px}.container{max-width:600px;margin:0 auto}.logo{font-size:1.5rem;font-weight:800;color:#fff;text-align:center;margin-bottom:8px}.logo span{background:linear-gradient(135deg,var(--blue),var(--orange));-webkit-background-clip:text;-webkit-text-fill-color:transparent}h1{text-align:center;color:#fff;font-size:1.8rem;margin-bottom:8px}p.sub{text-align:center;color:var(--muted);margin-bottom:32px;font-size:.9rem}label{display:block;color:var(--muted);font-size:.65rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}input,textarea{width:100%;background:var(--surface);border:1px solid var(--border);color:#fff;padding:14px 16px;border-radius:14px;font-size:.9rem;font-family:inherit;outline:none;margin-bottom:16px}input:focus,textarea:focus{border-color:var(--blue);box-shadow:0 0 0 3px var(--blue-glow)}textarea{resize:vertical;min-height:80px}.btn{background:var(--blue);color:#fff;border:none;padding:15px;border-radius:14px;font-weight:700;font-size:.9rem;cursor:pointer;width:100%}.btn:hover{opacity:.9}.result{background:var(--surface);border:1px solid #22c55e40;border-radius:16px;padding:24px;margin-top:20px;display:none}.result.active{display:block}.result .message{background:var(--bg);border:1px solid var(--border);border-radius:12px;padding:16px;font-size:.9rem;line-height:1.6;margin:12px 0;white-space:pre-wrap}.copy-btn{background:#22c55e;color:#fff;border:none;padding:10px 20px;border-radius:10px;font-weight:600;cursor:pointer;font-size:.8rem}.cta{text-align:center;margin-top:20px;color:var(--muted);font-size:.8rem}.cta a{color:var(--blue);text-decoration:none;font-weight:600}</style></head><body><div class='container'><div class='logo'><span>Follow-Up</span> OS</div><h1>Resurrect a Dead Lead</h1><p class='sub'>Paste the conversation. Get the exact message to send right now.</p><label>Your Name</label><input id='r_name' placeholder='How the client knows you'><label>Their Name</label><input id='r_theirName' placeholder='Client name'><label>Last Message</label><textarea id='r_lastMsg' placeholder='Paste the last message...'></textarea><label>What were you discussing?</label><input id='r_context' placeholder='e.g. branding project'><label>Days Since Last Contact</label><input id='r_days' type='number' value='7'><button class='btn' id='resurrectBtn' onclick='resurrect()'>Generate Message</button><div class='result' id='result'><p style='color:#22c55e;font-weight:700;margin-bottom:8px'>Your Re-engagement Message</p><div class='message' id='genMsg'></div><button class='copy-btn' onclick='copyMsg()'>📋 Copy Message</button></div><div class='cta'>Want to never lose a lead again? <a href='/app'>Try Follow-Up OS free →</a></div></div><script>async function resurrect(){const btn=document.getElementById('resurrectBtn');const orig=btn.innerHTML;btn.disabled=true;btn.innerHTML='Generating...';const r=await fetch('/api/resurrect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:document.getElementById('r_name').value,theirName:document.getElementById('r_theirName').value,lastMsg:document.getElementById('r_lastMsg').value,context:document.getElementById('r_context').value,days:document.getElementById('r_days').value})});const d=await r.json();document.getElementById('genMsg').textContent=d.message;document.getElementById('result').classList.add('active');btn.disabled=false;btn.innerHTML=orig}function copyMsg(){navigator.clipboard.writeText(document.getElementById('genMsg').textContent);alert('Message copied!')}</script></body></html>"""

LOGIN_PAGE = r"""<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1.0'><title>Login</title><style>:root{--bg:#06060e;--surface:#0c0c1a;--border:#1a1a35;--text:#e0e0e8;--muted:#7a7a90;--blue:#3b82f6;--blue-glow:#3b82f640;--orange:#ff6b35}*{margin:0;padding:0}body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}.card{background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:40px 32px;width:100%;max-width:420px;text-align:center}.logo{font-size:2rem;font-weight:800;color:#fff;margin-bottom:4px}.logo span{background:linear-gradient(135deg,var(--blue),var(--orange));-webkit-background-clip:text;-webkit-text-fill-color:transparent}p{color:var(--muted);font-size:.9rem;margin-bottom:32px}input{width:100%;background:var(--bg);border:1px solid var(--border);color:#fff;padding:14px 16px;border-radius:14px;font-size:.9rem;margin-bottom:16px;outline:none}input:focus{border-color:var(--blue);box-shadow:0 0 0 3px var(--blue-glow)}.btn{background:var(--blue);color:#fff;border:none;padding:15px;border-radius:14px;font-weight:700;font-size:.9rem;cursor:pointer;width:100%}.btn:hover{opacity:.9}.error{color:#ef4444;font-size:.8rem;margin-bottom:16px}.link{color:var(--muted);font-size:.8rem;margin-top:16px;display:block;text-decoration:none}.link:hover{color:var(--blue)}</style></head><body><div class='card'><div class='logo'><span>Follow-Up</span> OS</div><p>Never lose money from forgotten leads.</p><div id='error' class='error'></div><form onsubmit='login(event)'><input type='email' id='email' placeholder='Email' required><input type='password' id='password' placeholder='Password' required><button class='btn'>Login</button></form><a href='/signup' class='link'>Create account</a></div><script>async function login(e){e.preventDefault();const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:document.getElementById('email').value,password:document.getElementById('password').value})});if(r.ok)location.href='/app';else{const d=await r.json();document.getElementById('error').textContent=d.error}}</script></body></html>"""

SIGNUP_PAGE = r"""<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1.0'><title>Sign Up</title><style>:root{--bg:#06060e;--surface:#0c0c1a;--border:#1a1a35;--text:#e0e0e8;--muted:#7a7a90;--blue:#3b82f6;--blue-glow:#3b82f640;--orange:#ff6b35}*{margin:0;padding:0}body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}.card{background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:40px 32px;width:100%;max-width:420px;text-align:center}.logo{font-size:2rem;font-weight:800;color:#fff}.logo span{background:linear-gradient(135deg,var(--blue),var(--orange));-webkit-background-clip:text;-webkit-text-fill-color:transparent}p{color:var(--muted);font-size:.9rem;margin-bottom:32px}input{width:100%;background:var(--bg);border:1px solid var(--border);color:#fff;padding:14px 16px;border-radius:14px;font-size:.9rem;margin-bottom:16px;outline:none}input:focus{border-color:var(--blue)}.btn{background:var(--blue);color:#fff;border:none;padding:15px;border-radius:14px;font-weight:700;font-size:.9rem;cursor:pointer;width:100%}.btn:hover{opacity:.9}.error{color:#ef4444;font-size:.8rem;margin-bottom:16px}.link{color:var(--muted);font-size:.8rem;margin-top:16px;display:block;text-decoration:none}.link:hover{color:var(--blue)}</style></head><body><div class='card'><div class='logo'><span>Follow-Up</span> OS</div><p>Create your free account</p><div id='error' class='error'></div><form onsubmit='signup(event)'><input type='email' id='email' placeholder='Email' required><input type='password' id='password' placeholder='Password (6+ chars)' minlength='6' required><button class='btn'>Create Account</button></form><a href='/login' class='link'>Already have an account?</a></div><script>async function signup(e){e.preventDefault();const r=await fetch('/api/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:document.getElementById('email').value,password:document.getElementById('password').value})});if(r.ok)location.href='/app';else{const d=await r.json();document.getElementById('error').textContent=d.error}}</script></body></html>"""

APP_HTML = r"""<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1.0'><title>Follow-Up OS</title><style>:root{--bg:#06060e;--surface:#0c0c1a;--border:#1a1a35;--text:#e0e0e8;--muted:#7a7a90;--blue:#3b82f6;--blue-glow:#3b82f640;--orange:#ff6b35;--success:#22c55e;--warn:#f59e0b;--danger:#ef4444}*{margin:0;padding:0;box-sizing:border-box}body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;padding:24px}.container{max-width:960px;margin:0 auto}.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:28px;flex-wrap:wrap;gap:12px}.logo-text{font-size:1.4rem;font-weight:800;color:#fff}.logo-text span{background:linear-gradient(135deg,var(--blue),var(--orange));-webkit-background-clip:text;-webkit-text-fill-color:transparent}.topbar-right{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.streak{background:var(--surface);border:1px solid var(--blue);color:var(--blue);padding:6px 14px;border-radius:20px;font-size:.75rem;font-weight:600}.user-email{color:var(--muted);font-size:.8rem}.logout{color:var(--muted);text-decoration:none;font-size:.8rem;padding:8px 16px;background:var(--surface);border:1px solid var(--border);border-radius:20px}.logout:hover{border-color:var(--danger);color:var(--danger)}.save-banner{background:var(--surface);border:1px solid var(--warn);border-radius:16px;padding:20px 24px;margin-bottom:28px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;justify-content:center}.save-banner span{color:var(--warn);font-weight:600;font-size:.85rem}.save-banner input{background:var(--bg);border:1px solid var(--border);color:#fff;padding:12px 16px;border-radius:12px;font-size:.85rem;min-width:180px}.save-banner .btn-sm{background:var(--blue);color:#fff;border:none;padding:12px 20px;border-radius:12px;font-size:.85rem;font-weight:600;cursor:pointer}.summary{display:flex;gap:16px;margin-bottom:28px;flex-wrap:wrap}.summary-card{flex:1;min-width:140px;background:var(--surface);border:1px solid var(--border);border-radius:18px;padding:24px;text-align:center}.summary-card .num{font-size:2.4rem;font-weight:800}.summary-card .lbl{color:var(--muted);font-size:.7rem;text-transform:uppercase;letter-spacing:1px;margin-top:4px}.today{border-color:#3b82f640}.today .num{color:var(--blue)}.overdue{border-color:#ef444440}.overdue .num{color:var(--danger)}.active{border-color:#22c55e40}.active .num{color:var(--success)}.tabs{display:flex;gap:6px;margin-bottom:28px;flex-wrap:wrap}.tab{flex:1;min-width:100px;text-align:center;padding:14px 12px;border-radius:14px;cursor:pointer;font-weight:600;font-size:.8rem;color:var(--muted);background:var(--surface);border:1px solid var(--border)}.tab.active{background:var(--blue);color:#fff;border-color:var(--blue)}.tab .count{background:#fff;color:var(--blue);padding:2px 8px;border-radius:10px;font-size:.65rem;margin-left:6px;font-weight:800}.panel{display:none}.panel.active{display:block}.card{background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:32px;margin-bottom:20px}.card h3{color:var(--muted);font-size:.7rem;text-transform:uppercase;letter-spacing:2px;margin-bottom:20px}label{display:block;color:var(--muted);font-size:.65rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}input,textarea,select{width:100%;background:var(--bg);border:1px solid var(--border);color:#fff;padding:14px 16px;border-radius:14px;font-size:.9rem;font-family:inherit;outline:none;margin-bottom:16px}textarea{resize:vertical;min-height:60px}input:focus,textarea:focus,select:focus{border-color:var(--blue);box-shadow:0 0 0 3px var(--blue-glow)}.btn{background:var(--blue);color:#fff;border:none;padding:15px;border-radius:14px;font-weight:700;font-size:.9rem;cursor:pointer;width:100%}.btn:hover{opacity:.9}.btn-sm{background:var(--blue);color:#fff;border:none;padding:10px 16px;border-radius:12px;font-size:.75rem;cursor:pointer;font-weight:600}.btn-orange{background:var(--orange)}.btn-success{background:var(--success)}.btn-danger{background:var(--danger)}.btn-warn{background:var(--warn);color:#000}.quick-chip{background:var(--surface);border:1px solid var(--border);color:var(--muted);padding:8px 14px;border-radius:20px;font-size:.75rem;cursor:pointer;transition:.2s}.quick-chip:hover{border-color:var(--blue);color:var(--blue);background:#3b82f610}.lead-row{background:var(--bg);border:1px solid var(--border);border-radius:16px;padding:20px;margin:10px 0;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:14px}.lead-row .info{flex:1;min-width:200px}.lead-row .name{color:#fff;font-weight:600;font-size:1rem}.lead-row .detail{color:var(--muted);font-size:.75rem;margin-top:4px}.lead-row .actions{display:flex;gap:8px;flex-wrap:wrap}.badge{display:inline-block;padding:3px 10px;border-radius:12px;font-size:.65rem;font-weight:700}.badge.hot{background:#22c55e20;color:var(--success)}.badge.warm{background:#f59e0b20;color:var(--warn)}.badge.cold{background:#ef444420;color:var(--danger)}.badge.lost{background:#88888820;color:var(--muted)}.badge.closed{background:#22c55e40;color:#fff}.overdue-row{border-left:5px solid var(--danger)}.today-row{border-left:5px solid var(--blue)}.empty{text-align:center;color:var(--muted);padding:60px 20px;font-size:.9rem}.modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.85);z-index:999;align-items:center;justify-content:center}.modal.active{display:flex}.modal-content{background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:36px;max-width:440px;text-align:center}.modal-content h2{color:var(--success);margin-bottom:12px}.modal-content textarea{min-height:80px;margin-top:12px}.nudge-btn{background:transparent;border:1px solid var(--border);color:var(--muted);padding:6px 12px;border-radius:10px;font-size:.7rem;cursor:pointer}.nudge-btn.active{background:var(--warn);color:#000;border-color:var(--warn)}@media(max-width:640px){.topbar{flex-direction:column;text-align:center}.summary{flex-direction:column}.tabs{flex-direction:column}.lead-row{flex-direction:column;text-align:center}}</style></head><body><div class='container'><div class='topbar'><div class='logo-text'><span>Follow-Up</span> OS</div><div class='topbar-right'><span id='streakBadge' class='streak' style='display:none'></span><span class='user-email' id='userEmail'></span><a href='/api/logout' class='logout' id='logoutLink' style='display:none'>Logout</a></div></div><div id='saveBanner' class='save-banner' style='display:none'><span>⚠️ Your leads will be lost. Save them.</span><input type='email' id='bannerEmail' placeholder='Your email'><input type='password' id='bannerPassword' placeholder='Create password'><button class='btn-sm' onclick='saveAccount()'>Save My Leads</button><span id='bannerError' style='color:#ef4444;font-size:.75rem'></span></div><div class='summary' id='summary'></div><div class='tabs'><div class='tab active' onclick='switchTab(\"add\")'>➕ Add</div><div class='tab' onclick='switchTab(\"today\")'>🔥 Today<span class='count' id='todayCount'>0</span></div><div class='tab' onclick='switchTab(\"active\")'>📊 Active<span class='count' id='activeCount'>0</span></div><div class='tab' onclick='switchTab(\"lost\")'>📁 Closed</div></div><div id='add' class='panel active'><div class='card'><h3>Quick Add — Where did this lead come from?</h3><div style='display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px'><button class='quick-chip' onclick='setSource(\"WhatsApp\")'>💬 WhatsApp</button><button class='quick-chip' onclick='setSource(\"Instagram\")'>📷 Instagram</button><button class='quick-chip' onclick='setSource(\"Facebook\")'>👤 Facebook</button><button class='quick-chip' onclick='setSource(\"Telegram\")'>✈️ Telegram</button><button class='quick-chip' onclick='setSource(\"Email\")'>📧 Email</button><button class='quick-chip' onclick='setSource(\"Phone Call\")'>📞 Phone Call</button><button class='quick-chip' onclick='setSource(\"In-Person\")'>🤝 In-Person</button><button class='quick-chip' onclick='setSource(\"SMS\")'>💬 SMS</button><button class='quick-chip' onclick='setSource(\"Google\")'>🔍 Google</button><button class='quick-chip' onclick='setSource(\"Other\")'>📌 Other</button></div><label>Name</label><input id='l_name' placeholder='Client or business name'><label>Source</label><input id='l_source' placeholder='How did they contact you?'><label>Note</label><textarea id='l_note' placeholder='What do they need? Any context?'></textarea><div style='display:flex;gap:10px;flex-wrap:wrap'><div style='flex:1;min-width:150px'><label>Deal Value (₦)</label><input id='l_value' placeholder='e.g. 150000' type='number'></div><div style='flex:1;min-width:150px'><label>Status</label><select id='l_status'><option value='hot'>🔥 Hot</option><option value='warm' selected>🟡 Warm</option><option value='cold'>🔴 Cold</option></select></div><div style='flex:1;min-width:150px'><label>Follow-up Date</label><input id='l_date' type='date'></div></div><div style='display:flex;gap:10px;margin-top:8px'><button class='btn' onclick='addLead()' style='flex:2'>💾 Save Lead</button><button class='btn btn-orange' onclick='document.getElementById(\"importModal\").classList.add(\"active\")' style='flex:1'>📥 Import</button></div><div id='quickMsg' style='color:var(--success);font-size:.8rem;margin-top:8px;display:none'></div></div></div><div id='today' class='panel'><div class='card'><h3>Today's Follow-ups</h3><div id='todayList'><div class='empty'>Loading...</div></div></div></div><div id='active' class='panel'><div class='card'><h3>All Active Leads</h3><div id='activeList'><div class='empty'>Loading...</div></div></div></div><div id='lost' class='panel'><div class='card'><h3>Closed & Lost</h3><div id='lostList'><div class='empty'>Loading...</div></div></div></div></div><div class='modal' id='winModal'><div class='modal-content'><h2>🎉 Deal Closed!</h2><p id='winAmount' style='color:var(--text);margin-bottom:12px'></p><textarea id='winMessage' readonly></textarea><button class='btn btn-success' onclick='copyWin()' style='margin-top:8px'>📋 Copy & Share</button><button class='btn-sm' style='margin-top:10px;background:var(--muted)' onclick='closeModal()'>Close</button></div></div><div class='modal' id='importModal'><div class='modal-content' style='max-width:500px'><h2>📥 Import Leads</h2><p style='color:var(--muted);font-size:.8rem;margin-bottom:16px'>Upload a WhatsApp chat export (.txt) to extract contacts.</p><input type='file' id='importFile' accept='.txt' style='margin-bottom:12px'><button class='btn' onclick='importWhatsApp()'>Import from WhatsApp</button><div id='importResult' style='margin-top:12px;font-size:.8rem'></div><button class='btn-sm' style='margin-top:12px;background:var(--muted)' onclick='document.getElementById(\"importModal\").classList.remove(\"active\")'>Close</button></div></div><script>let current='add',isLoggedIn=false;fetch('/api/me').then(r=>r.json()).then(d=>{if(d.email){isLoggedIn=true;document.getElementById('userEmail').textContent=d.email;document.getElementById('logoutLink').style.display='inline';document.getElementById('saveBanner').style.display='none';if(d.streak>1){document.getElementById('streakBadge').textContent='🔥 '+d.streak+' day streak';document.getElementById('streakBadge').style.display='inline'}}else{document.getElementById('saveBanner').style.display='flex'}loadSummary()});function switchTab(t){current=t;document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));document.getElementById(t).classList.add('active');document.querySelector('.tab:nth-child('+(t==='add'?1:t==='today'?2:t==='active'?3:4)+')').classList.add('active');if(t==='today')loadToday();if(t==='active')loadActive();if(t==='lost')loadLost();loadSummary()}function loadSummary(){fetch('/api/summary').then(r=>r.json()).then(d=>{document.getElementById('summary').innerHTML='<div class=\"summary-card today\"><div class=\"num\">'+d.today+'</div><div class=\"lbl\">Due Today</div></div><div class=\"summary-card overdue\"><div class=\"num\">'+d.overdue+'</div><div class=\"lbl\">Overdue</div></div><div class=\"summary-card active\"><div class=\"num\">'+d.active+'</div><div class=\"lbl\">Active Pipeline</div></div>';document.getElementById('todayCount').textContent=d.today;document.getElementById('activeCount').textContent=d.active})}function renderLeads(leads,container){let h='';if(!leads.length)h='<div class=\"empty\">Nothing here.</div>';leads.forEach(l=>{let cls='';if(l.follow_up_date<new Date().toISOString().split('T')[0])cls='overdue-row';else if(l.follow_up_date===new Date().toISOString().split('T')[0])cls='today-row';h+='<div class=\"lead-row '+cls+'\"><div class=\"info\"><div class=\"name\">'+l.name+' <span class=\"badge '+l.status+'\">'+l.status.toUpperCase()+'</span></div><div class=\"detail\">₦'+(l.deal_value||0).toLocaleString()+' • '+l.follow_up_date+' • '+l.note+'</div></div><div class=\"actions\">';if(l.status!=='lost'&&l.status!=='closed'){h+='<button class=\"nudge-btn'+(l.nudge_enabled?' active':'')+'\" onclick=\"toggleNudge('+l.id+')\">🔔</button>';h+='<button class=\"btn-sm btn-success\" onclick=\"updateStatus('+l.id+',\\'closed\\')\">✅ Won</button>';h+='<button class=\"btn-sm btn-danger\" onclick=\"updateStatus('+l.id+',\\'lost\\')\">❌ Lost</button>';h+='<button class=\"btn-sm btn-warn\" onclick=\"followedUp('+l.id+')\">📞</button>'}h+='<button class=\"btn-sm\" onclick=\"downloadReminder('+l.id+')\">📅</button></div></div>'});document.getElementById(container).innerHTML=h}function loadToday(){fetch('/api/leads/today').then(r=>r.json()).then(d=>renderLeads(d,'todayList'))}function loadActive(){fetch('/api/leads/active').then(r=>r.json()).then(d=>renderLeads(d,'activeList'))}function loadLost(){fetch('/api/leads/lost').then(r=>r.json()).then(d=>renderLeads(d,'lostList'))}function setSource(s){document.getElementById('l_source').value=s;document.getElementById('quickMsg').textContent='Source: '+s;document.getElementById('quickMsg').style.display='block';setTimeout(function(){document.getElementById('quickMsg').style.display='none'},1500)}async function saveAccount(){const email=document.getElementById('bannerEmail').value;const password=document.getElementById('bannerPassword').value;if(!email||password.length<6){document.getElementById('bannerError').textContent='Enter valid email and password (6+ chars)';return}const r=await fetch('/api/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});if(r.ok)location.reload();else{const d=await r.json();document.getElementById('bannerError').textContent=d.error}}async function addLead(){const btn=document.querySelector('#add .btn');const orig=btn.innerHTML;btn.disabled=true;btn.innerHTML='Saving...';const r=await fetch('/api/leads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:document.getElementById('l_name').value,source:document.getElementById('l_source').value,note:document.getElementById('l_note').value,deal_value:document.getElementById('l_value').value,status:document.getElementById('l_status').value,follow_up_date:document.getElementById('l_date').value})});document.getElementById('l_name').value='';document.getElementById('l_note').value='';document.getElementById('l_value').value='';btn.disabled=false;btn.innerHTML=orig;loadSummary();if(!isLoggedIn)document.getElementById('saveBanner').style.display='flex'}async function updateStatus(id,status){await fetch('/api/leads/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})});if(status==='closed'){document.getElementById('winAmount').textContent='Deal closed!';document.getElementById('winMessage').value='Just closed another deal. Follow-Up OS keeps me organized.';document.getElementById('winModal').classList.add('active')}if(current==='today')loadToday();else if(current==='active')loadActive();else loadLost();loadSummary()}function closeModal(){document.getElementById('winModal').classList.remove('active')}function copyWin(){navigator.clipboard.writeText(document.getElementById('winMessage').value);alert('Copied!')}async function followedUp(id){let d=new Date();d.setDate(d.getDate()+3);await fetch('/api/leads/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({follow_up_date:d.toISOString().split('T')[0],last_contacted:new Date().toISOString()})});if(current==='today')loadToday();else loadActive();loadSummary()}async function toggleNudge(id){await fetch('/api/leads/'+id+'/nudge',{method:'POST'});if(current==='today')loadToday();else loadActive()}function downloadReminder(id){window.open('/api/leads/'+id+'/reminder','_blank')}async function importWhatsApp(){const file=document.getElementById('importFile').files[0];if(!file){document.getElementById('importResult').innerHTML='<span style=\"color:#ef4444\">Select a .txt file</span>';return}document.getElementById('importResult').innerHTML='Processing...';const form=new FormData();form.append('file',file);const r=await fetch('/api/import/whatsapp',{method:'POST',body:form});const d=await r.json();if(d.error){document.getElementById('importResult').innerHTML='<span style=\"color:#ef4444\">'+d.error+'</span>'}else{document.getElementById('importResult').innerHTML='<span style=\"color:#22c55e\">Found '+d.contacts.length+' contacts. Adding...</span>';for(const c of d.contacts){await fetch('/api/leads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:c.name,source:'WhatsApp Import',note:c.lastMessage||'',deal_value:0,status:'warm',follow_up_date:new Date().toISOString().split('T')[0]})})}document.getElementById('importResult').innerHTML='<span style=\"color:#22c55e\">✅ '+d.contacts.length+' leads imported!</span>';setTimeout(function(){document.getElementById('importModal').classList.remove('active');loadSummary();if(current==='active')loadActive()},1500)}}document.getElementById('l_date').value=new Date().toISOString().split('T')[0];loadSummary();</script></body></html>"""

COS_HTML = r"""<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1.0'><title>Cost of Silence</title><style>:root{--bg:#06060e;--surface:#0c0c1a;--border:#1a1a35;--text:#e0e0e8;--muted:#7a7a90;--blue:#3b82f6;--orange:#ff6b35;--danger:#ef4444}*{margin:0;padding:0}body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;align-items:center;justify-content:center;text-align:center;padding:24px}.container{max-width:640px}.logo{font-size:1.5rem;font-weight:800;color:#fff;margin-bottom:40px}.logo span{background:linear-gradient(135deg,var(--blue),var(--orange));-webkit-background-clip:text;-webkit-text-fill-color:transparent}.number{font-size:clamp(3rem,8vw,5rem);font-weight:800;color:var(--danger);line-height:1.1}.label{color:var(--muted);font-size:1rem;margin-bottom:36px}.stats{display:flex;gap:16px;justify-content:center;flex-wrap:wrap;margin-bottom:36px}.stat{background:var(--surface);border:1px solid var(--border);border-radius:18px;padding:24px 28px;min-width:150px}.stat .val{font-size:1.8rem;font-weight:700;color:var(--blue)}.stat .lbl{color:var(--muted);font-size:.7rem;text-transform:uppercase;margin-top:4px}.btn{display:inline-block;background:var(--blue);color:#fff;text-decoration:none;padding:16px 36px;border-radius:14px;font-weight:700;font-size:.95rem}.btn:hover{opacity:.9}</style></head><body><div class='container'><div class='logo'><span>Follow-Up</span> OS</div><div class='number' id='total'>...</div><div class='label'>in unclosed deals dying in DMs right now.</div><div class='stats'><div class='stat'><div class='val' id='daily'>...</div><div class='lbl'>Daily Loss</div></div><div class='stat'><div class='val' id='count'>...</div><div class='lbl'>Overdue</div></div></div><a href='/app' class='btn'>Stop Losing Money — Free</a></div><script>fetch('/api/public/cost-of-silence').then(r=>r.json()).then(d=>{document.getElementById('total').textContent='₦'+d.total_at_risk.toLocaleString();document.getElementById('daily').textContent='₦'+d.daily_loss_estimate.toLocaleString();document.getElementById('count').textContent=d.overdue_deals})</script></body></html>"""

# ROUTES
@app.get("/", response_class=HTMLResponse)
async def landing(): return LANDING_HTML

@app.get("/resurrect", response_class=HTMLResponse)
async def resurrect_page(): return RESURRECT_HTML

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_user(request): return RedirectResponse("/app")
    return LOGIN_PAGE

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(): return SIGNUP_PAGE

@app.get("/app", response_class=HTMLResponse)
async def app_page(): return APP_HTML

@app.get("/cost-of-silence", response_class=HTMLResponse)
async def cos_page(): return COS_HTML

@app.post("/api/resurrect")
async def resurrect_api(request: Request):
    data = await request.json()
    name = data.get("name","").strip()
    their_name = data.get("theirName","").strip()
    last_msg = data.get("lastMsg","").strip()
    context = data.get("context","").strip()
    days = data.get("days","7")
    greeting = f"Hey {their_name}" if their_name else "Hey"
    ctx = f"I was reviewing our conversation about {context}" if context else "I was going through old messages"
    urgency = "I realize I should have followed up sooner" if int(days) > 5 else "I wanted to follow up"
    msg = f"""{greeting},\n\n{urgency}. {ctx} and {last_msg[:80] if last_msg else 'our last chat'} came to mind.\n\nNo pressure at all — if you're still interested, I'd love to pick this back up. If things have changed, no worries either.\n\n{'- ' + name if name else '- [Your Name]'}"""
    return {"message": msg}

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
    ics = f"""BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Follow-Up OS//EN\nBEGIN:VEVENT\nDTSTART:{now.strftime('%Y%m%dT%H%M%S')}\nDTEND:{(now+timedelta(hours=1)).strftime('%Y%m%dT%H%M%S')}\nSUMMARY:Follow up with {lead['name']}\nBEGIN:VALARM\nTRIGGER:-PT15M\nACTION:DISPLAY\nDESCRIPTION:Time to follow up with {lead['name']}\nEND:VALARM\nEND:VEVENT\nEND:VCALENDAR"""
    return StreamingResponse(io.BytesIO(ics.encode()), media_type="text/calendar", headers={"Content-Disposition": f"attachment; filename=followup_{lead['name']}.ics"})

@app.post("/api/import/whatsapp")
async def import_whatsapp(file: UploadFile = File(...)):
    content = (await file.read()).decode("utf-8", errors="ignore")
    contacts = []
    lines = content.split("\n")
    for line in lines:
        line = line.strip()
        if not line: continue
        # Match WhatsApp format: "M/D/YY, H:MM - Name: Message"
        match = re.match(r'(\d+/\d+/\d+,\s+\d+:\d+)\s+-\s+(.+?):\s+(.+)', line)
        if match:
            name = match.group(2).strip()
            msg = match.group(3).strip()
            if name and name not in ["You", "System"] and not name.startswith("+"):
                contacts.append({"name": name, "lastMessage": msg[:100]})
        # Also try format: "[M/D/YY, H:MM:SS AM/PM] Name: Message"
        elif not contacts:
            match2 = re.match(r'\[(.+?)\]\s+(.+?):\s+(.+)', line)
            if match2:
                name = match2.group(2).strip()
                msg = match2.group(3).strip()
                if name and name not in ["You", "System"]:
                    contacts.append({"name": name, "lastMessage": msg[:100]})
    # Deduplicate
    seen = set()
    unique = []
    for c in contacts:
        if c["name"] not in seen:
            seen.add(c["name"])
            unique.append(c)
    return {"contacts": unique[:30]}

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    if request.cookies.get("admin_token") != ADMIN_PASS:
        return """<html><body style="background:#06060e;color:#fff;font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh"><form method="post" action="/dashboard/login"><input name="password" type="password" placeholder="Admin password" style="padding:14px;background:#0c0c1a;border:1px solid #1a1a35;color:#fff;border-radius:14px"><button style="padding:14px 24px;background:#3b82f6;color:#fff;border:none;border-radius:14px;cursor:pointer;font-weight:600;margin-top:8px">Access</button></form></body></html>"""
    rows = run_query("SELECT id, email, created, last_login, streak FROM users ORDER BY last_login DESC")
    html = "<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Dashboard</title><style>body{font-family:system-ui;background:#06060e;color:#d4d4d8;padding:40px}h1{color:#3b82f6}table{width:100%;border-collapse:collapse}th,td{padding:14px;text-align:left;border-bottom:1px solid #1a1a35}th{color:#3b82f6}.num{color:#22c55e;font-weight:700}</style></head><body><h1>Dashboard</h1><table><tr><th>Email</th><th>Leads</th><th>Signed Up</th><th>Last Login</th><th>Streak</th></tr>"
    for u in (rows or []):
        cnt = run_query("SELECT COUNT(*) FROM leads WHERE user_id=%s", (u["id"],))[0]["count"]
        html += f"<tr><td>{u['email']}</td><td class='num'>{cnt}</td><td>{u['created'][:10] if u['created'] else '-'}</td><td>{u['last_login'][:16] if u['last_login'] else 'Never'}</td><td>{u.get('streak',0) or 0} days</td></tr>"
    html += "</table></body></html>"
    return html

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
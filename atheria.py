#!/usr/bin/env python3
"""

Atheria Nexus — unified Jarvis-style core (Telegram + Web orb + city roles + supervised upgrade)
One process. You command; core proposes; you approve; core writes atheria_next.py only.
"""

import os, re, time, logging, sqlite3, threading, subprocess, shutil, tempfile, asyncio, json
from pathlib import Path
from urllib.parse import urlparse
import requests
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
KEY = (os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
OWNER = os.getenv("OWNER_ID", "").strip()
DB = Path(os.getenv("DB_PATH", str(BASE / "atheria.db")))
MODEL = os.getenv("MODEL", "openai/gpt-oss-120b").strip()
TTS_VOICE = os.getenv("TTS_VOICE", "fa-IR-DilaraNeural").strip()
VOICE_REPLY = os.getenv("VOICE_REPLY", "1").strip() == "1"
WHISPER = os.getenv("WHISPER_MODEL", "whisper-large-v3").strip()
WEB_PORT = int(os.getenv("WEB_PORT", "5500"))
GROQ = "https://api.groq.com/openai/v1/chat/completions"
STT = "https://api.groq.com/openai/v1/audio/transcriptions"
TG = f"https://api.telegram.org/bot{TOKEN}"
WORK = BASE / "workspace"
WORK.mkdir(exist_ok=True)
BAD = ["rm -rf", "sudo ", "drop table", "/dev/", "os.system("]

# Digital-city departments (prompt roles — not separate processes)
DEPTS = {
    "mayor": "Orchestrator: break goals, prioritize, safety, ask approval for risky acts.",
    "research": "Research: summarize, structure facts, cite uncertainty.",
    "code": "Engineer: write safe Python only, short runnable scripts.",
    "ops": "Operations: status, logs, next actions on device constraints.",
    "voice": "Companion: warm clear Persian replies, concise.",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("nexus")
STATE = {"msg": "Nexus online", "mode": "idle"}


def db():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init():
    with db() as c:
        c.executescript(
            """

            CREATE TABLE IF NOT EXISTS tasks(
              id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INT, goal TEXT, dept TEXT,
              status TEXT DEFAULT 'pending', response TEXT, created_at REAL, updated_at REAL);
            CREATE TABLE IF NOT EXISTS proposals(
              id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INT, title TEXT, body TEXT,
              status TEXT DEFAULT 'draft', created_at REAL);
            CREATE TABLE IF NOT EXISTS knowledge(
              id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INT, source TEXT, title TEXT,
              content TEXT, created_at REAL);
            CREATE TABLE IF NOT EXISTS journal(
              id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, note TEXT, created_at REAL);
            """

        )



def add_knowledge(cid, source, title, content):
    with db() as c:
        c.execute(
            "INSERT INTO knowledge(chat_id,source,title,content,created_at) VALUES(?,?,?,?,?)",
            (cid, (source or "")[:80], (title or "")[:120], (content or "")[:8000], time.time()),
        )
        c.commit()

def knowledge_blob(cid, limit=8):
    with db() as c:
        rows = c.execute(
            "SELECT title, content FROM knowledge WHERE chat_id=? OR chat_id IS NULL ORDER BY id DESC LIMIT ?",
            (cid, limit),
        ).fetchall()
    if not rows:
        return ""
    return "\n".join(f"- {r[0]}: {(r[1] or '')[:400]}" for r in rows)


def web_search(query, limit=6):
    """Read-only search via DuckDuckGo Instant Answer (no API key)."""
    q = (query or "").strip()
    if not q:
        return "عبارت جستجو خالی است."
    r = requests.get(
        "https://api.duckduckgo.com/",
        params={"q": q, "format": "json", "no_html": 1, "skip_disambig": 1},
        timeout=20,
        headers={"User-Agent": "AtheriaNexus/1.0"},
    )
    r.raise_for_status()
    data = r.json() if r.content else {}
    parts = []
    abs_text = (data.get("AbstractText") or "").strip()
    if abs_text:
        parts.append("خلاصه: " + abs_text[:900])
        if data.get("AbstractURL"):
            parts.append("منبع: " + str(data.get("AbstractURL"))[:300])
    related = data.get("RelatedTopics") or []
    n = 0
    for item in related:
        if n >= limit:
            break
        if not isinstance(item, dict):
            continue
        if item.get("Text"):
            line = "· " + str(item.get("Text"))[:220]
            if item.get("FirstURL"):
                line += " | " + str(item.get("FirstURL"))[:180]
            parts.append(line)
            n += 1
        for sub in item.get("Topics") or []:
            if n >= limit:
                break
            if isinstance(sub, dict) and sub.get("Text"):
                line = "· " + str(sub.get("Text"))[:220]
                if sub.get("FirstURL"):
                    line += " | " + str(sub.get("FirstURL"))[:180]
                parts.append(line)
                n += 1
    if not parts:
        return (
            "Instant Answer نتیجهٔ کافی نداد. "
            "یک URL مشخص را با /fetch باز کن یا عبارت را دقیق‌تر بنویس."
        )
    return "\n".join(parts)[:4000]


def journal(kind, note):
    with db() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS journal(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, note TEXT, created_at REAL)"
        )
        c.execute(
            "INSERT INTO journal(kind,note,created_at) VALUES(?,?,?)",
            ((kind or "")[:40], (note or "")[:2000], time.time()),
        )
        c.commit()

SYS_RULES = (
    "Atheria Nexus orchestrator. Persian when user is Persian. "
    "NEVER invent CPU/RAM stats, fake teams, tickets, or emails. "
    "If unsure, say what is missing. Code-core changes only via /upgrade+/approve+/apply. "
    "Use memory facts when present; prefer structure over long fluff."
)


def allowed(cid):
    return (not OWNER) or str(cid) == str(OWNER)


def bad(s):
    s = (s or "").lower()
    return any(x in s for x in BAD)


def pick_dept(text):
    t = (text or "").lower()
    if any(k in t for k in ("کد", "code", "اسکریپت", "python", "برنامه")):
        return "code"
    if any(k in t for k in ("تحقیق", "جستجو", "research", "تحلیل", "لینک")):
        return "research"
    if any(k in t for k in ("وضعیت", "status", "لاگ", "ارتقا", "upgrade")):
        return "ops"
    if any(k in t for k in ("ارتقا", "خودت", "upgrade", "تکامل")):
        return "mayor"
    return "voice"


def tg(cid, text):
    text = (text or "")[:4000]
    for i in range(1, 4):
        try:
            r = requests.post(f"{TG}/sendMessage", json={"chat_id": cid, "text": text}, timeout=30)
            if r.status_code == 200:
                return True
        except Exception as e:
            log.error("tg %s", e)
            time.sleep(2**i)
    return False


def speak(cid, text):
    STATE["msg"] = (text or "")[:120]
    STATE["mode"] = "speak"
    tg(cid, text)
    if not VOICE_REPLY:
        STATE["mode"] = "idle"
        return
    clip = re.sub(r"[#*_`]+", " ", text or "")
    clip = re.sub(r"\s+", " ", clip).strip()[:400]
    if not clip:
        STATE["mode"] = "idle"
        return
    path = Path(tempfile.gettempdir()) / f"nx{int(time.time()*1000)}.mp3"
    try:
        import edge_tts

        async def gen():
            await edge_tts.Communicate(clip, TTS_VOICE).save(str(path))

        asyncio.run(gen())
        with open(path, "rb") as f:
            requests.post(
                f"{TG}/sendAudio",
                data={"chat_id": cid, "title": "Atheria"},
                files={"audio": ("a.mp3", f)},
                timeout=60,
            )
    except Exception as e:
        log.error("tts %s", e)
        try:
            subprocess.Popen(["termux-tts-speak", clip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
    STATE["mode"] = "idle"


def llm(system, user, n=1500):
    if not KEY:
        return "API key missing in .env"
    h = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": n,
        "temperature": 0.4,
    }
    for i in range(1, 4):
        try:
            r = requests.post(GROQ, headers=h, json=body, timeout=120)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            if r.status_code in (429, 500, 502, 503):
                time.sleep(2**i)
                continue
            return f"API {r.status_code}: {r.text[:120]}"
        except Exception as e:
            if i == 3:
                return str(e)
            time.sleep(2**i)
    return "fail"


def py_block(t):
    m = re.search(r"```(?:python)?\s*([\s\S]*?)```", t or "")
    return (m.group(1) if m else t or "").strip()


def add_task(cid, goal, dept=None):
    dept = dept or pick_dept(goal)
    with db() as c:
        cur = c.execute(
            "INSERT INTO tasks(chat_id,goal,dept,status,created_at,updated_at) VALUES(?,?,?,'pending',?,?)",
            (cid, goal, dept, time.time(), time.time()),
        )
        c.commit()
        return int(cur.lastrowid), dept


def pop_task():
    with db() as c:
        r = c.execute("SELECT * FROM tasks WHERE status='pending' ORDER BY id LIMIT 1").fetchone()
        return dict(r) if r else None


def finish(tid, resp):
    with db() as c:
        c.execute(
            "UPDATE tasks SET status='completed', response=?, updated_at=? WHERE id=?",
            (resp, time.time(), tid),
        )
        c.commit()


def add_prop(cid, title, body):
    with db() as c:
        cur = c.execute(
            "INSERT INTO proposals(chat_id,title,body,status,created_at) VALUES(?,?,?,'draft',?)",
            (cid, title, body, time.time()),
        )
        c.commit()
        return int(cur.lastrowid)


def prop(pid):
    with db() as c:
        r = c.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None


def set_prop(pid, st):
    with db() as c:
        c.execute("UPDATE proposals SET status=? WHERE id=?", (st, pid))
        c.commit()


def stt(file_id):
    try:
        if not KEY:
            return "[stt no key]"
        r = requests.get(f"{TG}/getFile", params={"file_id": file_id}, timeout=30)
        r.raise_for_status()
        fp = r.json()["result"]["file_path"]
        data = requests.get(f"https://api.telegram.org/file/bot{TOKEN}/{fp}", timeout=60)
        data.raise_for_status()
        path = Path(tempfile.gettempdir()) / f"v{int(time.time())}.ogg"
        path.write_bytes(data.content)
        last = ""
        for model in (WHISPER, "whisper-large-v3", "whisper-large-v3-turbo"):
            for lang in ("fa", None):
                with open(path, "rb") as f:
                    form = {"model": model}
                    if lang:
                        form["language"] = lang
                    r2 = requests.post(
                        STT,
                        headers={"Authorization": f"Bearer {KEY}"},
                        files={"file": ("voice.ogg", f, "audio/ogg")},
                        data=form,
                        timeout=180,
                    )
                if r2.status_code == 200:
                    path.unlink(missing_ok=True)
                    return (r2.json().get("text") or "").strip()
                last = f"[stt {r2.status_code}]"
        path.unlink(missing_ok=True)
        return last
    except Exception as e:
        return f"[stt {e}]"


AGENTS = (
    ("research", "Research: structure, risks, open questions."),
    ("code", "Build: concrete steps or safe code ideas only."),
    ("ops", "Delivery: 48h checklist; what needs human approval."),
)
PULSE_SEC = int(os.getenv("PULSE_SEC", "180"))
_last_owner_chat = [None]

def set_owner_chat(cid):
    if cid:
        _last_owner_chat[0] = cid

def owner_chat():
    if OWNER and str(OWNER).isdigit():
        return int(OWNER)
    return _last_owner_chat[0]

def run_agent_pipeline(goal, chat_id):
    parts = []
    for name, role in AGENTS:
        STATE["msg"] = f"Agent [{name}]..."
        STATE["mode"] = "think"
        ans = llm(
            f"Atheria multi-agent network. You are {name}. {role} Persian, concise, professional.",
            f"Goal:\n{goal}\n\nEarlier:\n" + "\n".join(parts[-2:]),
            900,
        )
        parts.append(f"### {name}\n{ans}")
    return (
        "گزارش شبکه ایجنت‌ها\nهدف: " + goal + "\n\n" + "\n\n".join(parts)
        + "\n\nتغییر هسته فقط با /upgrade → /approve → /apply"
    )

def pulse_loop():
    while True:
        try:
            time.sleep(PULSE_SEC)
            with db() as c:
                n = c.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'").fetchone()[0]
                k = c.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
            STATE["msg"] = f"Pulse pending={n} knowledge={k}"
            journal("pulse", f"pending={n} knowledge={k}")
            cid = owner_chat()
            if cid and n >= 3:
                tg(cid, f"📡 نبض: {n} تسک در صف · دانش={k}\n/project /status /journal")
            elif cid and k > 0 and int(time.time()) % (PULSE_SEC * 10) < PULSE_SEC + 5:
                # occasional light status (not spam every pulse)
                pass
        except Exception as e:
            log.error("pulse %s", e)
            time.sleep(60)


def handle(cid, text):
    set_owner_chat(cid)
    if not allowed(cid):
        tg(cid, "دسترسی ندارید")
        return
    text = (text or "").strip()
    if text in ("/start", "/help", "سلام آتریا", "آتریا"):
        speak(
            cid,
            "شهر دیجیتال آتریا آنلاین است.\n"
            "ادارات: شهردار / تحقیق / کد / عملیات / همراه\n"
            "/seed هدف | ویس بفرست\n"
            "/code اسکریپت | /run فایل\n"
            "/upgrade قابلیت → /approve id → /apply id\n"
            "/city /status /last /journal\n/learn نکته | /fetch url\n"
            "وب: http://127.0.0.1:%s" % WEB_PORT,
        )
        return
    if text == "/city":
        with db() as c:
            n = c.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'").fetchone()[0]
            d = c.execute(
                "SELECT dept, COUNT(*) FROM tasks WHERE status='completed' GROUP BY dept"
            ).fetchall()
        lines = [f"Pending tasks: {n}", f"State: {STATE['mode']} | {STATE['msg'][:80]}"]
        for dept, cnt in d:
            lines.append(f"  {dept}: {cnt}")
        tg(cid, "\n".join(lines) if lines else "empty")
        return
    if text.startswith("/seed "):
        tid, dept = add_task(cid, text[6:].strip())
        tg(cid, f"Task #{tid} → dept [{dept}]")
        return
    if text.startswith("/code "):
        raw = llm(
            DEPTS["code"] + " One ```python``` block only. No destructive shell.",
            text[6:],
            1600,
        )
        code = py_block(raw)
        if bad(code):
            tg(cid, "blocked unsafe")
            return
        name = f"c{int(time.time())}.py"
        (WORK / name).write_text(code + "\n", encoding="utf-8")
        tg(cid, f"workspace/{name}\n/run {name}\n{code[:2400]}")
        return
    if text.startswith("/run "):
        name = text[5:].strip()
        if not re.fullmatch(r"[\w.\-]+", name):
            tg(cid, "bad name")
            return
        path = WORK / name
        if not path.exists():
            tg(cid, "missing")
            return
        try:
            p = subprocess.run(
                ["python", str(path)], cwd=str(WORK), capture_output=True, text=True, timeout=45
            )
            tg(cid, f"exit={p.returncode}\n{((p.stdout or '') + (p.stderr or ''))[-1800]}")
        except Exception as e:
            tg(cid, str(e))
        return
    if text.startswith("/upgrade "):
        goal = text[9:].strip()
        STATE["mode"] = "evolve"
        body = llm(
            "You design SAFE upgrades for Atheria Nexus (Telegram+Flask orb+SQLite+Groq). "
            "Output plan + full python module or patch in ```python```. Require human /approve /apply. "
            "Do not delete user data.",
            f"Upgrade request: {goal}",
            2000,
        )
        pid = add_prop(cid, goal[:80], body)
        STATE["mode"] = "idle"
        tg(
            cid,
            f"Proposal #{pid}\n1) /approve {pid}\n2) /apply {pid} → atheria_next.py\n"
            f"3) یک خط Termux که ربات می‌گوید\n\n{body[:1800]}",
        )
        return
    if text.startswith("/approve "):
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            tg(cid, "Usage: /approve id")
            return
        if not prop(int(parts[1])):
            tg(cid, "missing")
            return
        set_prop(int(parts[1]), "approved")
        tg(cid, f"approved #{parts[1]} → /apply {parts[1]}")
        return
    if text.startswith("/apply "):
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            tg(cid, "Usage: /apply id")
            return
        if OWNER and str(cid) != str(OWNER):
            tg(cid, "owner only")
            return
        p = prop(int(parts[1]))
        if not p or p["status"] not in ("approved", "draft"):
            tg(cid, "need proposal")
            return
        code = py_block(p["body"])
        if len(code) < 100 or bad(code):
            tg(cid, "no safe full python block — در /upgrade بخواه فایل کامل بدهد")
            return
        bak = BASE / f"bak_{int(time.time())}.py"
        if (BASE / "atheria.py").exists():
            shutil.copy2(BASE / "atheria.py", bak)
        (BASE / "atheria_next.py").write_text(code + "\n", encoding="utf-8")
        set_prop(int(parts[1]), "written_next")
        tg(
            cid,
            f"wrote atheria_next.py (backup {bak.name})\n"
            "Termux:\n"
            "cp atheria_next.py atheria.py; pkill -f atheria.py; "
            "nohup python atheria.py > atheria.log 2>&1 &",
        )
        return
    if text == "/status":
        with db() as c:
            rows = c.execute(
                "SELECT status,COUNT(*) FROM tasks WHERE chat_id=? GROUP BY status", (cid,)
            ).fetchall()
        tg(cid, " | ".join(f"{a}:{b}" for a, b in rows) if rows else "empty")
        return
    if text == "/last":
        with db() as c:
            r = c.execute(
                "SELECT * FROM tasks WHERE chat_id=? ORDER BY id DESC LIMIT 1", (cid,)
            ).fetchone()
        if not r:
            tg(cid, "empty")
            return
        r = dict(r)
        tg(cid, f"#{r['id']} [{r.get('dept')}] {r['goal']}\n{r.get('response') or ''}"[:3900])
        return

    if text.startswith("/learn "):
        note = text[7:].strip()
        add_knowledge(cid, "user", note[:80], note)
        journal("learn", note[:500])
        tg(cid, "ثبت در حافظه شد.")
        return
    if text.startswith("/fetch "):
        url = text[7:].strip().split()[0]
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "AtheriaNexus/1.0"})
            raw = r.text[:5000]
            summary = llm(
                SYS_RULES + " Summarize page for the user in Persian; list facts; note uncertainty.",
                f"URL: {url}\n\nCONTENT:\n{raw[:3500]}",
                900,
            )
            add_knowledge(cid, "web", url[:120], summary[:4000])
            journal("fetch", url[:200])
            speak(cid, summary[:3000])
        except Exception as e:
            tg(cid, f"fetch error: {e}")
        return

    if text == "/search" or text == "/جستجو" or text.startswith("/search ") or text.startswith("/جستجو "):
        q = text.split(" ", 1)[1].strip() if " " in text else ""
        if not q:
            tg(cid, "استفاده: /search عبارت مورد نظر")
            return
        try:
            tg(cid, f"جستجو: {q[:80]}…")
            raw = web_search(q)
            summary = llm(
                SYS_RULES
                + " From search snippets only, answer in Persian. "
                + "List facts and links if present. If evidence is weak, say so. Do not invent sources.",
                f"QUERY: {q}\n\nRESULTS:\n{raw}",
                900,
            )
            add_knowledge(cid, "search", q[:120], (summary or raw)[:4000])
            journal("search", q[:200])
            speak(cid, (summary or raw)[:3000])
        except Exception:
            logging.exception("web search failed")
            tg(cid, "جستجو انجام نشد؛ کمی بعد دوباره تلاش کن.")
        return

    if text in ("/journal", "/گزارش"):
        with db() as c:
            rows = c.execute(
                "SELECT kind, note, created_at FROM journal ORDER BY id DESC LIMIT 12"
            ).fetchall()
        if not rows:
            tg(cid, "ژورنال خالی است.")
            return
        lines = [f"· {r[0]}: {(r[1] or '')[:120]}" for r in rows]
        tg(cid, "ژورنال اخیر:\n" + "\n".join(lines))
        return

    if text.startswith("/project ") or text.startswith("پروژه "):
        goal = text.split(" ", 1)[1].strip()
        tg(cid, "شبکه ایجنت‌ها مشغول پروژه…")
        report = run_agent_pipeline(goal, cid)
        try:
            add_knowledge(cid, "project", goal[:80], report[:4000])
        except Exception:
            pass
        speak(cid, report[:3500])
        return
    if text.strip() in ("/pulse", "نبض"):
        tg(cid, f"نبض زنده · هر {PULSE_SEC} ثانیه")
        return
    # free text / voice transcript
    tid, dept = add_task(cid, text)
    tg(cid, f"Task #{tid} [{dept}]")





def make_tts_file(text, out: Path):
    clip = re.sub(r"[#*_`]+", " ", text or "")
    clip = re.sub(r"\s+", " ", clip).strip()[:450]
    if not clip:
        return False
    try:
        import edge_tts
        async def gen():
            await edge_tts.Communicate(clip, TTS_VOICE).save(str(out))
        asyncio.run(gen())
        return out.exists() and out.stat().st_size > 100
    except Exception as e:
        log.error("make_tts %s", e)
        return False




def start_web():
    try:
        from flask import Flask, jsonify, request, send_file
    except ImportError:
        log.warning("Flask missing")
        return
    app = Flask(__name__)
    tts_path = BASE / "workspace" / "web_tts.mp3"

    UI = r"""

<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1"/>
<title>ATHERIA · JARVIS NODE</title>
<style>
:root{
  --bg:#070b12; --panel:rgba(12,18,28,.72); --line:rgba(125,211,252,.22);
  --c:#7dd3fc; --c2:#38bdf8; --acc:#a78bfa; --ok:#34d399; --text:#e8f4ff; --muted:#8ba3b8;
}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:var(--bg);color:var(--text);
font-family:ui-sans-serif,system-ui,-apple-system,sans-serif;overflow-x:hidden}
/* neural net canvas */
#net{position:fixed;inset:0;z-index:0;opacity:.45}
.vignette{position:fixed;inset:0;z-index:1;pointer-events:none;
background:radial-gradient(ellipse at 50% 30%,transparent 0%,rgba(7,11,18,.4) 50%,rgba(7,11,18,.92) 100%)}
.wrap{position:relative;z-index:2;max-width:440px;margin:0 auto;padding:20px 14px 32px}
.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.brand{font-size:.68rem;letter-spacing:.28em;color:var(--c);text-shadow:0 0 18px rgba(125,211,252,.5)}
.iconbtn{background:var(--panel);border:1px solid var(--line);color:var(--c);border-radius:10px;
padding:8px 10px;font-size:.75rem;backdrop-filter:blur(12px);cursor:pointer}
/* presence */
.stage{position:relative;height:200px;display:flex;align-items:center;justify-content:center;margin:6px 0 10px}
.ring{position:absolute;border-radius:50%;border:1px solid rgba(125,211,252,.15)}
.r1{width:180px;height:180px;animation:spin 28s linear infinite}
.r2{width:140px;height:140px;border-color:rgba(167,139,250,.2);animation:spin 18s linear infinite reverse}
.core{width:88px;height:88px;border-radius:50%;position:relative;z-index:2;
background:radial-gradient(circle at 35% 30%,#e0f2fe 0%,#38bdf8 25%,#0ea5e9 45%,#0c4a6e 75%,#020617 100%);
box-shadow:0 0 40px rgba(56,189,248,.45),0 0 80px rgba(14,165,233,.2),inset 0 0 20px rgba(255,255,255,.25);
transition:transform .35s,box-shadow .35s}
.core.listen{box-shadow:0 0 50px rgba(167,139,250,.6);transform:scale(1.06);
background:radial-gradient(circle at 35% 30%,#f5f3ff,#a78bfa 40%,#5b21b6 80%)}
.core.think{animation:pulse 1.4s ease-in-out infinite}
.core.speak{transform:scale(1.1);box-shadow:0 0 60px rgba(56,189,248,.7)}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes pulse{50%{transform:scale(1.05);opacity:.92}}
/* glass status */
.glass{background:var(--panel);border:1px solid var(--line);border-radius:16px;
backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
box-shadow:0 8px 32px rgba(0,0,0,.35),inset 0 1px 0 rgba(255,255,255,.06)}
#status{min-height:52px;padding:12px 14px;margin:0 0 12px;font-size:.9rem;line-height:1.55;text-align:center}
/* agents C */
.agents{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px}
.ag{padding:10px 6px;text-align:center;font-size:.65rem}
.ag b{display:block;font-size:.72rem;color:var(--c);margin-bottom:4px;font-weight:600}
.ag .st{color:var(--muted)}.ag.on .st{color:var(--ok)}
/* controls */
.row{display:flex;gap:8px;margin-bottom:10px}
button.main{flex:1;border:0;border-radius:14px;padding:13px 10px;font-weight:600;font-size:.85rem;cursor:pointer;
background:linear-gradient(135deg,#0ea5e9,#6366f1);color:#fff;box-shadow:0 8px 24px rgba(14,165,233,.25)}
button.ghost{flex:1;border-radius:14px;padding:13px 10px;font-size:.85rem;cursor:pointer;
background:var(--panel);border:1px solid var(--line);color:var(--text);backdrop-filter:blur(12px)}
input#inp{width:100%;padding:13px 14px;border-radius:14px;border:1px solid var(--line);
background:rgba(8,12,20,.85);color:var(--text);font-size:.9rem;outline:none;margin-bottom:10px}
input#inp:focus{border-color:var(--c2);box-shadow:0 0 0 3px rgba(56,189,248,.15)}
#log{max-height:110px;overflow:auto;font-size:.75rem;padding:10px 12px;color:var(--muted);text-align:right}
#log div{margin-bottom:6px}
/* settings drawer */
#drawer{display:none;position:fixed;inset:0;z-index:50;background:rgba(0,0,0,.55);backdrop-filter:blur(4px)}
#drawer.open{display:flex;align-items:flex-end;justify-content:center}
.sheet{width:100%;max-width:440px;max-height:78vh;overflow:auto;border-radius:20px 20px 0 0;
padding:18px 16px 28px;background:rgba(10,14,22,.94);border:1px solid var(--line)}
.sheet h3{margin:0 0 14px;font-size:1rem;color:var(--c)}
.field{margin-bottom:14px}
.field label{display:block;font-size:.72rem;color:var(--muted);margin-bottom:6px}
.field select,.field input[type=range]{width:100%}
.field select{padding:10px;border-radius:10px;background:#0c121c;border:1px solid var(--line);color:var(--text)}
.toggles{display:flex;flex-wrap:wrap;gap:8px}
.tog{padding:8px 12px;border-radius:999px;border:1px solid var(--line);font-size:.72rem;cursor:pointer;color:var(--muted)}
.tog.on{border-color:var(--c);color:var(--c);background:rgba(125,211,252,.1)}
.hint{font-size:.65rem;color:var(--muted);margin-top:8px;text-align:center;opacity:.7}
</style>
</head>
<body>
<canvas id="net"></canvas>
<div class="vignette"></div>
<div class="wrap">
  <div class="top">
    <div class="brand">ATHERIA · CORE</div>
    <button class="iconbtn" id="btnSet" type="button">تنظیمات</button>
  </div>
  <div class="stage">
    <div class="ring r1"></div><div class="ring r2"></div>
    <div class="core" id="core"></div>
  </div>
  <div class="glass" id="status">سیستم آماده. یک‌بار «صدا» را بزن، بعد فرمان بده.</div>
  <div class="agents" id="agentRow">
    <div class="glass ag" id="a-research"><b>Research</b><span class="st">idle</span></div>
    <div class="glass ag" id="a-code"><b>Code</b><span class="st">idle</span></div>
    <div class="glass ag" id="a-ops"><b>Ops</b><span class="st">idle</span></div>
  </div>
  <div class="row">
    <button class="main" id="unlock" type="button">🔊 صدا</button>
    <button class="main" id="mic" type="button">🎙 صحبت</button>
    <button class="ghost" id="stop" type="button">توقف</button>
  </div>
  <input id="inp" placeholder="فرمان متنی برای آتریا…"/>
  <div class="glass" id="log"></div>
  <div class="hint">صدا از سرور (edge-tts) · داده روی دستگاه</div>
</div>
<audio id="aud" playsinline></audio>
<div id="drawer"><div class="sheet">
  <h3>تنظیمات نمایش</h3>
  <div class="field"><label>تم رنگی</label>
    <select id="theme">
      <option value="cyan">Cyan Jarvis</option>
      <option value="violet">Violet Neural</option>
      <option value="emerald">Emerald Ops</option>
      <option value="amber">Amber Command</option>
    </select>
  </div>
  <div class="field"><label>شدت شبکه عصبی</label>
    <input type="range" id="netOp" min="10" max="80" value="45"/>
  </div>
  <div class="field"><label>نمایش‌ها</label>
    <div class="toggles">
      <span class="tog on" data-k="agents">ایجنت‌ها</span>
      <span class="tog on" data-k="log">لاگ</span>
      <span class="tog on" data-k="rings">حلقه‌ها</span>
      <span class="tog on" data-k="net">شبکه</span>
    </div>
  </div>
  <div class="field"><label>اندازه حضور مرکزی</label>
    <input type="range" id="coreSz" min="70" max="120" value="88"/>
  </div>
  <button class="main" id="closeSet" type="button" style="width:100%">بستن</button>
</div></div>
<script>
const core=document.getElementById('core'), status=document.getElementById('status');
const logEl=document.getElementById('log'), aud=document.getElementById('aud');
const canvas=document.getElementById('net'), ctx=canvas.getContext('2d');
let nodes=[], anim=0, cfg=JSON.parse(localStorage.getItem('ath_ui')||'{}');
const themes={
 cyan:{c:'#7dd3fc',c2:'#38bdf8',acc:'#a78bfa'},
 violet:{c:'#c4b5fd',c2:'#a78bfa',acc:'#f0abfc'},
 emerald:{c:'#6ee7b7',c2:'#34d399',acc:'#2dd4bf'},
 amber:{c:'#fcd34d',c2:'#fbbf24',acc:'#fb923c'}
};
function applyTheme(name){
  const t=themes[name]||themes.cyan;
  document.documentElement.style.setProperty('--c',t.c);
  document.documentElement.style.setProperty('--c2',t.c2);
  document.documentElement.style.setProperty('--acc',t.acc);
}
function save(){localStorage.setItem('ath_ui',JSON.stringify(cfg))}
function mode(m){core.className='core'+(m?' '+m:'')}
function add(a,b){const d=document.createElement('div');d.textContent=a+' · '+(b||'').slice(0,140);logEl.prepend(d)}
function setAgent(name,on){
  const el=document.getElementById('a-'+name); if(!el)return;
  el.classList.toggle('on',!!on); el.querySelector('.st').textContent=on?'active':'idle';
}
async function playUrl(url){
  try{aud.src=url+'?t='+Date.now();mode('speak');await aud.play();aud.onended=()=>mode('')}
  catch(e){status.textContent='پخش: '+e}
}
async function ask(text){
  if(!text||!text.trim())return;
  add('YOU',text);mode('think');status.textContent='پردازش…';
  setAgent('research',true);
  try{
    const r=await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text:text.trim()})});
    const j=await r.json();
    setAgent('research',false); setAgent(j.dept==='code'?'code':j.dept==='ops'?'ops':'research',true);
    const rep=j.reply||'—'; status.textContent=rep; add('ATHERIA',rep);
    if(j.audio) await playUrl(j.audio); else mode('');
    setTimeout(()=>{setAgent('research',0);setAgent('code',0);setAgent('ops',0)},2500);
  }catch(e){status.textContent='ارتباط قطع — بعداً دوباره';mode('');}
}
document.getElementById('unlock').onclick=()=>ask('به اختصار بگو آنلاین هستم');
document.getElementById('stop').onclick=()=>{try{speechSynthesis.cancel()}catch(e){}aud.pause();mode('');status.textContent='آماده'};
const SR=window.SpeechRecognition||window.webkitSpeechRecognition; let rec=null;
if(SR){rec=new SR();rec.lang='fa-IR';rec.onresult=e=>ask(e.results[0][0].transcript);
  const go=e=>{e.preventDefault();mode('listen');status.textContent='گوش می‌دهم…';try{rec.start()}catch(x){}};
  const end=()=>{try{rec.stop()}catch(x){}};
  mic.addEventListener('mousedown',go);mic.addEventListener('touchstart',go,{passive:false});
  mic.addEventListener('mouseup',end);mic.addEventListener('touchend',end);
}else mic.onclick=()=>status.textContent='از ورودی متن استفاده کن';
inp.onkeydown=e=>{if(e.key==='Enter'){ask(inp.value);inp.value=''}};
/* settings */
const drawer=document.getElementById('drawer');
btnSet.onclick=()=>drawer.classList.add('open');
closeSet.onclick=()=>drawer.classList.remove('open');
theme.value=cfg.theme||'cyan'; applyTheme(theme.value);
theme.onchange=()=>{cfg.theme=theme.value;applyTheme(theme.value);save()};
netOp.value=cfg.netOp||45; netOp.oninput=()=>{cfg.netOp=+netOp.value;canvas.style.opacity=(cfg.netOp/100);save()};
coreSz.value=cfg.coreSz||88; coreSz.oninput=()=>{cfg.coreSz=+coreSz.value;core.style.width=core.style.height=cfg.coreSz+'px';save()};
document.querySelectorAll('.tog').forEach(el=>{
  const k=el.dataset.k; if(cfg['hide_'+k]) el.classList.remove('on');
  el.onclick=()=>{el.classList.toggle('on');cfg['hide_'+k]=!el.classList.contains('on');save();applyVis()};
});
function applyVis(){
  agentRow.style.display=cfg.hide_agents?'none':'grid';
  logEl.style.display=cfg.hide_log?'none':'block';
  document.querySelectorAll('.ring').forEach(r=>r.style.display=cfg.hide_rings?'none':'block');
  canvas.style.display=cfg.hide_net?'none':'block';
}
applyVis(); canvas.style.opacity=(cfg.netOp||45)/100;
/* neural background */
function resize(){canvas.width=innerWidth;canvas.height=innerHeight}
function initNet(){
  nodes=[]; const n=Math.min(48, Math.floor(innerWidth/18));
  for(let i=0;i<n;i++) nodes.push({x:Math.random()*canvas.width,y:Math.random()*canvas.height,
    vx:(Math.random()-.5)*.25,vy:(Math.random()-.5)*.25});
}
function drawNet(){
  ctx.clearRect(0,0,canvas.width,canvas.height);
  const col=getComputedStyle(document.documentElement).getPropertyValue('--c').trim()||'#7dd3fc';
  for(const p of nodes){p.x+=p.vx;p.y+=p.vy; if(p.x<0||p.x>canvas.width)p.vx*=-1; if(p.y<0||p.y>canvas.height)p.vy*=-1}
  for(let i=0;i<nodes.length;i++) for(let j=i+1;j<nodes.length;j++){
    const a=nodes[i],b=nodes[j],d=Math.hypot(a.x-b.x,a.y-b.y);
    if(d<120){ctx.strokeStyle=col;ctx.globalAlpha=.12*(1-d/120);ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke()}
  }
  ctx.globalAlpha=.7; ctx.fillStyle=col;
  for(const p of nodes){ctx.beginPath();ctx.arc(p.x,p.y,1.4,0,6.3);ctx.fill()}
  ctx.globalAlpha=1; requestAnimationFrame(drawNet);
}
addEventListener('resize',()=>{resize();initNet()}); resize();initNet();drawNet();
</script>
</body></html>
"""


    @app.route("/")
    def index():
        return UI

    @app.route("/api/state")
    def api_state():
        return jsonify(STATE)

    @app.route("/api/tts.mp3")
    def api_tts():
        if tts_path.exists():
            return send_file(tts_path, mimetype="audio/mpeg")
        return ("", 404)

    @app.route("/api/command", methods=["POST"])
    def api_command():
        data = request.get_json(force=True, silent=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"reply": "سیگنال خالی", "audio": None})
        dept = pick_dept(text)
        role = DEPTS.get(dept, DEPTS["voice"])
        STATE["mode"] = "think"
        STATE["msg"] = text[:80]
        reply = llm(
            f"Atheria Jarvis-style companion. {role} "
            "Warm precise Persian, short paragraphs. Never invent CPU/RAM or fake teams. "
            "Real code upgrades only via Telegram /upgrade.",
            text,
            900,
        )
        audio = None
        try:
            tts_path.parent.mkdir(exist_ok=True)
            if make_tts_file(reply, tts_path):
                audio = "/api/tts.mp3"
        except Exception as e:
            log.error("web tts %s", e)
        STATE["mode"] = "speak"
        STATE["msg"] = (reply or "")[:100]
        return jsonify({"reply": reply, "dept": dept, "audio": audio})

    def run():
        app.run(host="0.0.0.0", port=WEB_PORT, debug=False, use_reloader=False)

    threading.Thread(target=run, daemon=True).start()
    log.info("Jarvis UI on :%s", WEB_PORT)


class App:
    def __init__(self):
        self.off = 0
        self.ok = True

    def poll(self):
        while self.ok:
            try:
                r = requests.get(
                    f"{TG}/getUpdates", params={"offset": self.off, "timeout": 25}, timeout=40
                )
                if r.status_code != 200:
                    time.sleep(5)
                    continue
                for u in r.json().get("result", []):
                    self.off = max(self.off, u["update_id"] + 1)
                    m = u.get("message") or {}
                    cid = (m.get("chat") or {}).get("id")
                    if not cid:
                        continue
                    if m.get("voice"):
                        t = stt(m["voice"]["file_id"])
                        tg(cid, f"heard: {t[:800]}")
                        if t and not str(t).startswith("["):
                            handle(cid, t)
                    elif (m.get("text") or "").strip():
                        handle(cid, m["text"].strip())
            except Exception as e:
                log.error("poll %s", e)
                time.sleep(8)

    def work(self):
        while self.ok:
            try:
                t = pop_task()
                if not t:
                    time.sleep(3)
                    continue
                dept = t.get("dept") or "voice"
                role = DEPTS.get(dept, DEPTS["voice"])
                STATE["msg"] = f"Working #{t['id']} [{dept}]"
                STATE["mode"] = "think"
                mem = knowledge_blob(t.get("chat_id") or 0)
                ans = llm(
                    SYS_RULES + f" Role: {role}",
                    (f"Memory:\n{mem}\n\n" if mem else "") + f"Goal:\n{t['goal']}",
                    1500,
                )
                try:
                    add_knowledge(t.get("chat_id"), "task", str(t.get("goal"))[:80], ans[:2000])
                except Exception:
                    pass
                finish(t["id"], ans)
                speak(t["chat_id"], f"Done #{t['id']} [{dept}]\n{ans[:2800]}")
            except Exception as e:
                log.error("work %s", e)
                time.sleep(5)

    def run(self):
        if not TOKEN:
            log.error("TELEGRAM_BOT_TOKEN missing")
            return
        init()
        start_web()
        log.info("Atheria Nexus up model=%s web=%s", MODEL, WEB_PORT)
        STATE["msg"] = "Atheria Nexus online"
        threading.Thread(target=self.poll, daemon=True).start()
        threading.Thread(target=self.work, daemon=True).start()
        threading.Thread(target=pulse_loop, daemon=True).start()
        while True:
            time.sleep(1)


if __name__ == "__main__":
    App().run()

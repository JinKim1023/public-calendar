# app.py (Render 무료 플랜용)
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import sqlite3, datetime
from pathlib import Path

# ★ 앱 폴더 내부에 DB 파일을 저장 (디스크 없이 동작)
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = str((BASE_DIR / "events.db").resolve())
AUTO_APPROVE = "true"  # Render 환경변수로 바꿔도 되지만 기본값은 true

app = FastAPI(title="Public Calendar")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ★ 절대경로로 static 마운트 (어디서 실행해도 안전)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

@app.get("/", response_class=HTMLResponse)
def root():
    return FileResponse(str(BASE_DIR / "static" / "index.html"))

# --- DB 초기화 ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        date TEXT NOT NULL,
        start_time TEXT,
        end_time TEXT,
        location TEXT,
        description TEXT,
        status TEXT NOT NULL DEFAULT 'approved',
        created_at TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()

init_db()

# --- API ---
@app.get("/events")
def list_events(status: str = "approved"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
      SELECT id, title, date, start_time, end_time, location, description, status
      FROM events
      WHERE status=?
      ORDER BY date, COALESCE(start_time,'00:00')
    """, (status,))
    rows = c.fetchall()
    conn.close()

    items = []
    for _id, title, date, start, end, loc, desc, st in rows:
        if start:
            items.append({
                "id": _id,
                "title": title,
                "start": f"{date}T{start}:00",
                "end": f"{date}T{(end or start)}:00",
                "extendedProps": {"location": loc, "description": desc, "status": st}
            })
        else:
            items.append({
                "id": _id,
                "title": title,
                "start": date,
                "allDay": True,
                "extendedProps": {"location": loc, "description": desc, "status": st}
            })
    return JSONResponse(items)

@app.post("/events")
def create_event(
    title: str = Form(...),
    date: str = Form(...),              # YYYY-MM-DD
    timeslot: str = Form("하루종일"),     # 오전/오후/하루종일
    location: str = Form(""),
    description: str = Form("")
):
    try:
        datetime.date.fromisoformat(date)
    except Exception:
        raise HTTPException(status_code=400, detail="날짜 형식은 YYYY-MM-DD")

    slot = (timeslot or "").strip()
    if "하루" in slot or "종일" in slot:
        start_time, end_time = None, None
    elif "오전" in slot or slot.lower()=="am":
        start_time, end_time = "09:00", "13:00"
    elif "오후" in slot or slot.lower()=="pm":
        start_time, end_time = "13:00", "18:00"
    else:
        start_time, end_time = "09:00", "13:00"

    status = "approved" if AUTO_APPROVE == "true" else "pending"
    created_at = datetime.datetime.utcnow().isoformat()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
      INSERT INTO events (title, date, start_time, end_time, location, description, status, created_at)
      VALUES (?,?,?,?,?,?,?,?)
    """, (title.strip()[:100], date, start_time, end_time, location.strip()[:120], description.strip(), status, created_at))
    conn.commit()
    new_id = c.lastrowid
    conn.close()

    return {"ok": True, "id": new_id, "status": status}

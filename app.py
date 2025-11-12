# app.py — 간단 폼 + 삭제 기능 포함 (Render 무료 플랜 OK)
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import sqlite3, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = str((BASE_DIR / "events.db").resolve())
AUTO_APPROVE = "true"  # 필요시 환경변수로 바꿔도 됨

app = FastAPI(title="구매팀 캘린더")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

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
        title TEXT NOT NULL,   -- 예: 김성현 (오전)
        date TEXT NOT NULL,    -- YYYY-MM-DD
        start_time TEXT,       -- HH:MM (없으면 종일)
        end_time TEXT,
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
      SELECT id, title, date, start_time, end_time, status
      FROM events
      WHERE status=?
      ORDER BY date, COALESCE(start_time,'00:00')
    """, (status,))
    rows = c.fetchall()
    conn.close()

    items = []
    for _id, title, date, start, end, st in rows:
        if start:
            items.append({
                "id": _id,
                "title": title,
                "start": f"{date}T{start}:00",
                "end": f"{date}T{(end or start)}:00",
            })
        else:
            items.append({
                "id": _id,
                "title": title,
                "start": date,
                "allDay": True,
            })
    return JSONResponse(items)

@app.post("/events")
def create_event(
    name: str = Form(...),               # ✅ 사용자명
    date: str = Form(...),               # YYYY-MM-DD
    timeslot: str = Form("하루종일"),     # 오전/오후/하루종일
):
    # 날짜 검증
    try:
        datetime.date.fromisoformat(date)
    except Exception:
        raise HTTPException(status_code=400, detail="날짜 형식은 YYYY-MM-DD")

    # 캘린더 제목: "이름 (오전/오후/하루종일)"
    slot = (timeslot or "").strip()
    if "하루" in slot or "종일" in slot:
        label = "하루종일"
        start_time, end_time = None, None
    elif "오전" in slot or slot.lower() == "am":
        label = "오전"
        start_time, end_time = "09:00", "13:00"
    elif "오후" in slot or slot.lower() == "pm":
        label = "오후"
        start_time, end_time = "13:00", "18:00"
    else:
        label = "오전"
        start_time, end_time = "09:00", "13:00"

    title = f"{name} ({label})"
    status = "approved" if AUTO_APPROVE == "true" else "pending"
    created_at = datetime.datetime.utcnow().isoformat()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
      INSERT INTO events (title, date, start_time, end_time, status, created_at)
      VALUES (?,?,?,?,?,?)
    """, (title, date, start_time, end_time, status, created_at))
    conn.commit()
    new_id = c.lastrowid
    conn.close()

    return {"ok": True, "id": new_id, "status": status}

@app.delete("/events/{event_id}")
def delete_event(event_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM events WHERE id=?", (event_id,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    if deleted == 0:
        raise HTTPException(status_code=404, detail="해당 이벤트가 없습니다.")
    return {"ok": True, "id": event_id}

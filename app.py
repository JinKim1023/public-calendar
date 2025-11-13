# app.py — Supabase(Postgres) 버전 (간단 폼 + 삭제 기능)
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import datetime
import os
import psycopg2  # ✅ Postgres(Supabase) 연결용

BASE_DIR = Path(__file__).resolve().parent

# Render 환경변수에서 AUTO_APPROVE, DATABASE_URL 읽기
AUTO_APPROVE = os.getenv("AUTO_APPROVE", "true").lower() == "true"
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("환경변수 DATABASE_URL 이 설정되어 있지 않습니다.")

def get_conn():
    # Supabase는 SSL 필요 → sslmode='require'
    return psycopg2.connect(DATABASE_URL, sslmode="require")

app = FastAPI(title="구매팀 캘린더 (Supabase DB)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# 정적 파일 & 루트
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

@app.get("/", response_class=HTMLResponse)
def root():
    return FileResponse(str(BASE_DIR / "static" / "index.html"))

# --- DB 초기화 (테이블 없으면 생성) ---
def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,   -- 예: 김성현 (오전)
            date TEXT NOT NULL,    -- YYYY-MM-DD
            start_time TEXT,       -- HH:MM (없으면 종일)
            end_time TEXT,
            status TEXT NOT NULL DEFAULT 'approved',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    cur.close()
    conn.close()

init_db()

# --- API: 조회 ---
@app.get("/events")
def list_events(status: str = "approved"):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, title, date, start_time, end_time, status
        FROM events
        WHERE status = %s
        ORDER BY date, COALESCE(start_time, '00:00')
        """,
        (status,),
    )
    rows = cur.fetchall()
    cur.close()
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

# --- API: 생성 ---
@app.post("/events")
def create_event(
    name: str = Form(...),               # 사용자명
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
    status = "approved" if AUTO_APPROVE else "pending"
    created_at = datetime.datetime.utcnow().isoformat()

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO events (title, date, start_time, end_time, status, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (title, date, start_time, end_time, status, created_at),
    )
    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    return {"ok": True, "id": new_id, "status": status}

# --- API: 삭제 ---
@app.delete("/events/{event_id}")
def delete_event(event_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM events WHERE id = %s", (event_id,))
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()

    if deleted == 0:
        raise HTTPException(status_code=404, detail="해당 이벤트가 없습니다.")
    return {"ok": True, "id": event_id}

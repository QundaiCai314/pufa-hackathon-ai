import os
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy import create_engine, text

router = APIRouter(tags=["auth"])
DATABASE_URL = os.getenv("DATABASE_URL", "")
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "qingpu-change-this-secret")
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    user_type: str = "customer"
    admin_code: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class SessionRequest(BaseModel):
    name: Optional[str] = None
    role: str = "customer_service"

class MessageRequest(BaseModel):
    role: str
    content: str
    metadata: Optional[dict] = None

def db():
    if not DATABASE_URL:
        raise HTTPException(503, "数据库未配置")
    return create_engine(DATABASE_URL)

def token_for(user):
    return jwt.encode({"sub": str(user["id"]), "username": user["username"], "exp": datetime.now(timezone.utc) + timedelta(days=7)}, SECRET_KEY, algorithm=ALGORITHM)

def current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "请先登录")
    try:
        payload = jwt.decode(authorization[7:], SECRET_KEY, algorithms=[ALGORITHM])
        uid = payload.get("sub")
        if not uid: raise JWTError()
    except JWTError:
        raise HTTPException(401, "登录已失效，请重新登录")
    with db().connect() as conn:
        row = conn.execute(text("SELECT id, username, email, is_admin, user_type FROM users WHERE id=:id AND is_active=TRUE"), {"id": uid}).mappings().first()
    if not row: raise HTTPException(401, "用户不存在或已停用")
    return dict(row)

def ensure_chat_tables():
    with db().begin() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS chat_sessions (id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), user_id UUID REFERENCES users(id) ON DELETE CASCADE, session_name VARCHAR(255), assistant_role VARCHAR(32) DEFAULT 'customer_service', memory_summary TEXT, created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW())"""))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS user_type VARCHAR(16) DEFAULT 'customer'"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS memory_summary TEXT"))
        conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS assistant_role VARCHAR(32) DEFAULT 'customer_service'"))
        conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS lead_score INTEGER DEFAULT 0"))
        conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS lead_level VARCHAR(16) DEFAULT 'low'"))
        conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS lead_signals JSONB DEFAULT '{}'::jsonb"))
        conn.execute(text("""CREATE TABLE IF NOT EXISTS chat_messages (id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE, role VARCHAR(20) NOT NULL, content TEXT NOT NULL, metadata JSONB, created_at TIMESTAMP DEFAULT NOW())"""))

@router.post("/register")
def register(req: RegisterRequest):
    if len(req.username.strip()) < 2 or len(req.password) < 6:
        raise HTTPException(400, "用户名至少2位，密码至少6位")
    ensure_chat_tables()
    user_type = req.user_type if req.user_type in ("customer", "admin") else "customer"
    if user_type == "admin":
        expected = os.getenv("ADMIN_REGISTRATION_CODE", "qingpu-admin-2026")
        if not req.admin_code or req.admin_code != expected:
            raise HTTPException(403, "管理用户注册口令错误")
    try:
        with db().begin() as conn:
            row = conn.execute(text("INSERT INTO users(username,email,hashed_password,user_type,is_admin) VALUES(:u,:e,:p,:t,:a) RETURNING id,username,email,is_admin,user_type"), {"u":req.username.strip(),"e":req.email.strip(),"p":pwd_context.hash(req.password),"t":user_type,"a":user_type == "admin"}).mappings().first()
        user=dict(row)
        return {"token": token_for(user), "user": user}
    except Exception as e:
        if "unique" in str(e).lower(): raise HTTPException(409, "用户名或邮箱已存在")
        raise HTTPException(500, "注册失败")

@router.post("/login")
def login(req: LoginRequest):
    with db().connect() as conn:
        row=conn.execute(text("SELECT id,username,email,hashed_password,is_admin,user_type FROM users WHERE username=:u OR email=:u"), {"u":req.username.strip()}).mappings().first()
    if not row or not pwd_context.verify(req.password, row["hashed_password"]): raise HTTPException(401,"用户名或密码错误")
    user={k:row[k] for k in ("id","username","email","is_admin","user_type")}
    return {"token":token_for(user),"user":user}

@router.get("/me")
def me(user=Depends(current_user)): return {"user":user}

@router.get("/sessions")
def sessions(user=Depends(current_user)):
    with db().connect() as conn:
        rows=conn.execute(text("SELECT id,session_name,assistant_role,lead_score,lead_level,lead_signals,created_at,updated_at FROM chat_sessions WHERE user_id=:u ORDER BY updated_at DESC"),{"u":user["id"]}).mappings().all()
    return {"sessions":[dict(r) for r in rows]}

@router.post("/sessions")
def create_session(req: SessionRequest, user=Depends(current_user)):
    with db().begin() as conn:
        row=conn.execute(text("INSERT INTO chat_sessions(user_id,session_name,assistant_role) VALUES(:u,:n,:r) RETURNING id,session_name,assistant_role,created_at,updated_at"),{"u":user["id"],"n":req.name or "新会话","r":req.role if req.role in ("customer_service","sales","technical_support") else "customer_service"}).mappings().first()
    return {"session":dict(row)}

@router.put("/sessions/{session_id}/role")
def update_session_role(session_id: str, req: SessionRequest, user=Depends(current_user)):
    role = req.role if req.role in ("customer_service", "sales", "technical_support") else "customer_service"
    with db().begin() as conn:
        row = conn.execute(text("UPDATE chat_sessions SET assistant_role=:r, updated_at=NOW() WHERE id=:s AND user_id=:u RETURNING assistant_role"), {"r":role,"s":session_id,"u":user["id"]}).mappings().first()
        if not row: raise HTTPException(404, "会话不存在")
    return {"assistant_role": row["assistant_role"]}

@router.get("/sessions/{session_id}/lead")
def session_lead(session_id: str, user=Depends(current_user)):
    with db().connect() as conn:
        row=conn.execute(text("SELECT lead_score,lead_level,lead_signals FROM chat_sessions WHERE id=:s AND user_id=:u"), {"s":session_id,"u":user["id"]}).mappings().first()
    if not row: raise HTTPException(404, "会话不存在")
    return dict(row)

@router.get("/sessions/{session_id}/messages")
def get_messages(session_id: str, user=Depends(current_user)):
    with db().connect() as conn:
        ok=conn.execute(text("SELECT 1 FROM chat_sessions WHERE id=:s AND user_id=:u"),{"s":session_id,"u":user["id"]}).first()
        if not ok: raise HTTPException(404,"会话不存在")
        rows=conn.execute(text("SELECT id,role,content,metadata,created_at FROM chat_messages WHERE session_id=:s ORDER BY created_at"),{"s":session_id}).mappings().all()
    return {"messages":[dict(r) for r in rows]}

@router.post("/sessions/{session_id}/messages")
def save_message(session_id: str, req: MessageRequest, user=Depends(current_user)):
    with db().begin() as conn:
        ok=conn.execute(text("SELECT 1 FROM chat_sessions WHERE id=:s AND user_id=:u"),{"s":session_id,"u":user["id"]}).first()
        if not ok: raise HTTPException(404,"会话不存在")
        row=conn.execute(text("INSERT INTO chat_messages(session_id,role,content,metadata) VALUES(:s,:r,:c,CAST(:m AS JSONB)) RETURNING id,created_at"),{"s":session_id,"r":req.role,"c":req.content,"m":json.dumps(req.metadata or {}, ensure_ascii=False)}).mappings().first()
        conn.execute(text("UPDATE chat_sessions SET updated_at=NOW() WHERE id=:s"),{"s":session_id})
    return {"message":dict(row)}

@router.get("/sessions/{session_id}/memory")
def session_memory(session_id: str, user=Depends(current_user)):
    """返回长期摘要与最近 6 条原文，供下一轮模型调用。"""
    with db().connect() as conn:
        session = conn.execute(text("SELECT memory_summary FROM chat_sessions WHERE id=:s AND user_id=:u"), {"s":session_id,"u":user["id"]}).mappings().first()
        if not session: raise HTTPException(404, "会话不存在")
        rows = conn.execute(text("SELECT role,content FROM chat_messages WHERE session_id=:s ORDER BY created_at DESC LIMIT 6"), {"s":session_id}).mappings().all()
    history = []
    if session["memory_summary"]: history.append({"role":"system","content":"以下是此前对话的长期记忆，请据此保持上下文一致：\n" + session["memory_summary"]})
    history += [{"role":r["role"],"content":r["content"]} for r in reversed(rows)]
    return {"history": history}

@router.post("/sessions/{session_id}/compact")
async def compact_session(session_id: str, user=Depends(current_user)):
    """消息超过阈值时压缩旧上下文；原始消息保留用于用户查看。"""
    from app.services.llm_service import llm_service
    with db().connect() as conn:
        session = conn.execute(text("SELECT memory_summary FROM chat_sessions WHERE id=:s AND user_id=:u"), {"s":session_id,"u":user["id"]}).mappings().first()
        if not session: raise HTTPException(404, "会话不存在")
        rows = conn.execute(text("SELECT role,content FROM chat_messages WHERE session_id=:s ORDER BY created_at"), {"s":session_id}).mappings().all()
    if len(rows) <= 12: return {"compacted":False}
    old = rows[:-6]
    transcript = "\n".join(f"{'用户' if r['role']=='user' else '助手'}：{r['content']}" for r in old)
    summary = await llm_service.summarize_memory(session["memory_summary"] or "", transcript)
    with db().begin() as conn:
        conn.execute(text("UPDATE chat_sessions SET memory_summary=:m, updated_at=NOW() WHERE id=:s"), {"m":summary,"s":session_id})
    return {"compacted":True}

@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, user=Depends(current_user)):
    with db().begin() as conn:
        result=conn.execute(text("DELETE FROM chat_sessions WHERE id=:s AND user_id=:u"),{"s":session_id,"u":user["id"]})
    if result.rowcount==0: raise HTTPException(404,"会话不存在")
    return {"ok":True}

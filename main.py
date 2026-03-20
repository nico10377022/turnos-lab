from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
import os

app = FastAPI()

# =========================
# CORS
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# BASE DE DATOS (LOCAL + PRODUCCIÓN)
# =========================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///turnos.db")

# fix Render (postgres:// → postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")

# conexión según tipo
if DATABASE_URL.startswith("postgresql"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"sslmode": "require"}
    )
else:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )

# =========================
# CREAR TABLAS
# =========================
with engine.begin() as conn:
    
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS equipos (
        id SERIAL PRIMARY KEY,
        nombre TEXT UNIQUE
    )
    """))

    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS turnos (
        id SERIAL PRIMARY KEY,
        equipo_id INT,
        inicio TEXT,
        fin TEXT,
        usuario TEXT
    )
    """))

    conn.execute(text("""
    INSERT INTO equipos (id, nombre) VALUES
    (1, 'GC-FID'),
    (2, 'FAAS'),
    (3, 'Liofilizador')
    ON CONFLICT DO NOTHING
    """))

# =========================
# LIMPIEZA AUTOMÁTICA
# =========================
def limpiar_turnos_vencidos():
    limite = datetime.now() - timedelta(days=2)

    with engine.begin() as conn:
        conn.execute(text("""
        DELETE FROM turnos
        WHERE datetime(fin) < :limite
        """), {"limite": limite.isoformat()})

# =========================
# ROOT
# =========================
@app.get("/")
def home():
    return {"ok": True}

# =========================
# FRONTEND
# =========================
@app.get("/app")
def app_web():
    return FileResponse("index.html")

# =========================
# CREAR TURNO
# =========================
@app.post("/turno")
def crear_turno(equipo_id: int, inicio: str, fin: str, usuario: str):

    limpiar_turnos_vencidos()

    inicio_dt = datetime.fromisoformat(inicio)
    fin_dt = datetime.fromisoformat(fin)

    if fin_dt <= inicio_dt:
        raise HTTPException(status_code=400, detail="Horario inválido")

    with engine.begin() as conn:

        conflicto = conn.execute(text("""
        SELECT * FROM turnos
        WHERE equipo_id = :equipo_id
        AND inicio < :fin
        AND fin > :inicio
        """), {
            "equipo_id": equipo_id,
            "inicio": inicio,
            "fin": fin
        }).fetchone()

        if conflicto:
            raise HTTPException(status_code=400, detail="Equipo ocupado")

        conn.execute(text("""
        INSERT INTO turnos (equipo_id, inicio, fin, usuario)
        VALUES (:equipo_id, :inicio, :fin, :usuario)
        """), {
            "equipo_id": equipo_id,
            "inicio": inicio,
            "fin": fin,
            "usuario": usuario
        })

    return {"status": "ok"}

# =========================
# VER TURNOS
# =========================
@app.get("/turnos/{equipo_id}")
def ver_turnos(equipo_id: int):

    limpiar_turnos_vencidos()

    with engine.connect() as conn:
        result = conn.execute(text("""
        SELECT * FROM turnos
        WHERE equipo_id = :equipo_id
        ORDER BY inicio
        """), {"equipo_id": equipo_id}).fetchall()

    return [dict(row._mapping) for row in result]

# =========================
# ELIMINAR TURNO
# =========================
@app.delete("/turno/{turno_id}")
def eliminar_turno(turno_id: int):
    with engine.begin() as conn:
        conn.execute(text("""
        DELETE FROM turnos WHERE id = :id
        """), {"id": turno_id})

    return {"status": "eliminado"}

# =========================
# RUN LOCAL
# =========================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
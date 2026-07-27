"""
data/database.py — Capa de Acceso a Datos (SQLite)
===================================================
Módulo centralizado para todas las operaciones con la base de datos.
Usa aiosqlite para operaciones asíncronas y no bloquear el event loop.

Instalación:
    pip install aiosqlite

Tablas:
    guild_config  — Configuración por servidor (canales, roles)
    warnings      — Registro de advertencias de moderación
    notes         — Notas personales del dueño
    tasks         — Tareas pendientes del dueño

Por qué un módulo separado:
    - Centraliza todas las queries SQL en un solo lugar.
    - Los cogs no conocen los detalles de la DB; solo llaman funciones.
    - Si en el futuro se migra a PostgreSQL, solo cambia este archivo.
"""

import aiosqlite
from datetime import datetime

import config


# ---------------------------------------------------------------------------
# Inicialización — crear tablas si no existen
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """
    Crea todas las tablas necesarias si no existen.
    Se llama UNA VEZ en main.py al arrancar el bot (en setup_hook).

    Las tablas usan IF NOT EXISTS para ser idempotentes:
    se puede llamar esta función en cada arranque sin riesgo.
    """
    async with aiosqlite.connect(config.DB_PATH) as db:

        # Configuración por servidor (guild)
        # Un registro por servidor; se actualiza con UPSERT al configurar.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id         INTEGER PRIMARY KEY,
                welcome_channel  INTEGER DEFAULT NULL,   -- ID del canal de bienvenidas
                farewell_channel INTEGER DEFAULT NULL,   -- ID del canal de despedidas
                default_role     INTEGER DEFAULT NULL    -- ID del rol que se asigna al entrar
            )
        """)

        # Registro de advertencias de moderación
        # Permite múltiples advertencias por usuario; se consultan por guild+user.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason      TEXT    NOT NULL,
                created_at  TEXT    NOT NULL    -- ISO 8601: "2025-01-15T10:30:00"
            )
        """)

        # Notas personales del dueño
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id   INTEGER NOT NULL,
                content    TEXT    NOT NULL,
                created_at TEXT    NOT NULL
            )
        """)

        # Tareas del dueño
        # status puede ser: "pending" | "done"
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id     INTEGER NOT NULL,
                content      TEXT    NOT NULL,
                status       TEXT    NOT NULL DEFAULT 'pending',
                created_at   TEXT    NOT NULL,
                completed_at TEXT    DEFAULT NULL
            )
        """)

        await db.commit()

    print("  ✅ Base de datos inicializada correctamente.")


# ---------------------------------------------------------------------------
# guild_config — Configuración por servidor
# ---------------------------------------------------------------------------

async def get_guild_config(guild_id: int) -> dict:
    """
    Obtiene la configuración completa de un servidor desde la base de datos.

    Args:
        guild_id: ID del servidor de Discord.

    Returns:
        Dict con claves: welcome_channel, farewell_channel, default_role.
        Los valores son int (ID de Discord) o None si no están configurados.
    """
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row   # Permite acceder columnas por nombre
        async with db.execute(
            "SELECT * FROM guild_config WHERE guild_id = ?",
            (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        # El servidor nunca fue configurado; retornar valores por defecto
        return {"welcome_channel": None, "farewell_channel": None, "default_role": None}

    return dict(row)


async def set_guild_config(guild_id: int, **fields) -> None:
    """
    Crea o actualiza la configuración de un servidor (UPSERT).

    UPSERT = INSERT o UPDATE si ya existe el registro.
    Permite actualizar solo los campos que se pasan como kwargs.

    Args:
        guild_id: ID del servidor de Discord.
        **fields: Campos a actualizar. Claves válidas:
                  welcome_channel, farewell_channel, default_role.

    Example:
        await set_guild_config(12345, welcome_channel=67890)
        await set_guild_config(12345, default_role=11111, farewell_channel=22222)
    """
    valid_fields = {"welcome_channel", "farewell_channel", "default_role"}
    filtered = {k: v for k, v in fields.items() if k in valid_fields}

    if not filtered:
        return

    # Construir la query dinámicamente con los campos recibidos
    columns      = ", ".join(filtered.keys())
    placeholders = ", ".join("?" * len(filtered))
    updates      = ", ".join(f"{col} = excluded.{col}" for col in filtered)
    values       = list(filtered.values())

    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            f"""
            INSERT INTO guild_config (guild_id, {columns})
            VALUES (?, {placeholders})
            ON CONFLICT(guild_id) DO UPDATE SET {updates}
            """,
            [guild_id, *values],
        )
        await db.commit()


# ---------------------------------------------------------------------------
# warnings — Advertencias de moderación
# ---------------------------------------------------------------------------

async def add_warning(
    guild_id:     int,
    user_id:      int,
    moderator_id: int,
    reason:       str,
) -> int:
    """
    Registra una nueva advertencia en la base de datos.

    Args:
        guild_id:     ID del servidor.
        user_id:      ID del usuario que recibe la advertencia.
        moderator_id: ID del moderador que la aplica.
        reason:       Motivo de la advertencia.

    Returns:
        ID numérico de la advertencia recién creada.
    """
    created_at = datetime.utcnow().isoformat()

    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, moderator_id, reason, created_at),
        )
        await db.commit()
        return cursor.lastrowid


async def get_warnings(guild_id: int, user_id: int) -> list[dict]:
    """
    Obtiene todas las advertencias de un usuario en un servidor.

    Args:
        guild_id: ID del servidor.
        user_id:  ID del usuario a consultar.

    Returns:
        Lista de dicts con claves: id, moderator_id, reason, created_at.
        Lista vacía si el usuario no tiene advertencias.
    """
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, moderator_id, reason, created_at
            FROM warnings
            WHERE guild_id = ? AND user_id = ?
            ORDER BY created_at ASC
            """,
            (guild_id, user_id),
        ) as cursor:
            rows = await cursor.fetchall()

    return [dict(row) for row in rows]


async def clear_warnings(guild_id: int, user_id: int) -> int:
    """
    Elimina todas las advertencias de un usuario en un servidor.

    Args:
        guild_id: ID del servidor.
        user_id:  ID del usuario.

    Returns:
        Número de advertencias eliminadas.
    """
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await db.commit()
        return cursor.rowcount


# ---------------------------------------------------------------------------
# notes — Notas del dueño
# ---------------------------------------------------------------------------

async def add_note(owner_id: int, content: str) -> int:
    """
    Guarda una nueva nota personal.

    Args:
        owner_id: ID de Discord del dueño.
        content:  Texto de la nota.

    Returns:
        ID numérico de la nota creada.
    """
    created_at = datetime.utcnow().isoformat()

    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO notes (owner_id, content, created_at) VALUES (?, ?, ?)",
            (owner_id, content, created_at),
        )
        await db.commit()
        return cursor.lastrowid


async def get_notes(owner_id: int) -> list[dict]:
    """
    Obtiene todas las notas del dueño ordenadas de más reciente a más antigua.

    Args:
        owner_id: ID de Discord del dueño.

    Returns:
        Lista de dicts con claves: id, content, created_at.
    """
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, content, created_at FROM notes WHERE owner_id = ? ORDER BY created_at DESC",
            (owner_id,),
        ) as cursor:
            rows = await cursor.fetchall()

    return [dict(row) for row in rows]


async def delete_note(owner_id: int, note_id: int) -> bool:
    """
    Elimina una nota específica del dueño.

    Args:
        owner_id: ID de Discord del dueño (para verificar que le pertenece).
        note_id:  ID de la nota a eliminar.

    Returns:
        True si la nota existía y fue eliminada, False si no se encontró.
    """
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM notes WHERE id = ? AND owner_id = ?",
            (note_id, owner_id),
        )
        await db.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# tasks — Tareas del dueño
# ---------------------------------------------------------------------------

async def add_task(owner_id: int, content: str) -> int:
    """
    Crea una nueva tarea con estado 'pending'.

    Args:
        owner_id: ID de Discord del dueño.
        content:  Descripción de la tarea.

    Returns:
        ID numérico de la tarea creada.
    """
    created_at = datetime.utcnow().isoformat()

    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO tasks (owner_id, content, status, created_at) VALUES (?, ?, 'pending', ?)",
            (owner_id, content, created_at),
        )
        await db.commit()
        return cursor.lastrowid


async def get_tasks(owner_id: int, status: str = "pending") -> list[dict]:
    """
    Obtiene las tareas del dueño filtradas por estado.

    Args:
        owner_id: ID de Discord del dueño.
        status:   "pending" | "done" | "all"

    Returns:
        Lista de dicts con claves: id, content, status, created_at, completed_at.
    """
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        if status == "all":
            query  = "SELECT * FROM tasks WHERE owner_id = ? ORDER BY created_at DESC"
            params = (owner_id,)
        else:
            query  = "SELECT * FROM tasks WHERE owner_id = ? AND status = ? ORDER BY created_at DESC"
            params = (owner_id, status)

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

    return [dict(row) for row in rows]


async def complete_task(owner_id: int, task_id: int) -> bool:
    """
    Marca una tarea como completada.

    Args:
        owner_id: ID de Discord del dueño (verificación de pertenencia).
        task_id:  ID de la tarea a completar.

    Returns:
        True si la tarea existía y fue actualizada, False si no se encontró.
    """
    completed_at = datetime.utcnow().isoformat()

    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            """
            UPDATE tasks
            SET status = 'done', completed_at = ?
            WHERE id = ? AND owner_id = ? AND status = 'pending'
            """,
            (completed_at, task_id, owner_id),
        )
        await db.commit()
        return cursor.rowcount > 0

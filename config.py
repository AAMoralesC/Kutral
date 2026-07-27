"""
config.py — Configuración Global de Kutral
==========================================
Centraliza todas las constantes y variables de entorno del bot.
Cualquier módulo que necesite configuración debe importar desde aquí,
NUNCA directamente desde os.getenv().

Dependencias:
    pip install python-dotenv
"""

import os
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Variables de Entorno
# ---------------------------------------------------------------------------

load_dotenv()

# Token de autenticación del bot (obligatorio)
TOKEN: str = os.getenv("DISCORD_TOKEN", "")

# ID de Discord del dueño del bot (para comandos privados)
# Se convierte a int porque Discord usa IDs numéricos de 64 bits (Snowflakes)
OWNER_ID: int = int(os.getenv("OWNER_ID", "0"))

# ---------------------------------------------------------------------------
# Google Gemini — IA
# Obtén tu API key en: https://aistudio.google.com/app/apikey
# ---------------------------------------------------------------------------

# Proveedor de IA (por ahora solo "gemini" está implementado)
AI_PROVIDER: str = os.getenv("AI_PROVIDER", "gemini")

# API Key de Gemini
AI_API_KEY: str = os.getenv("AI_API_KEY", "")

# Modelo a usar en Groq. Opciones recomendadas:
#   "llama-3.3-70b-versatile" → potente y equilibrado (RECOMENDADO)
#   "llama3-8b-8192"          → más rápido y ligero
#   "mixtral-8x7b-32768"      → excelente para contextos muy largos
AI_MODEL: str = os.getenv("AI_MODEL", "llama-3.3-70b-versatile")

# ---------------------------------------------------------------------------
# Spotify — Credenciales de la API
# Crea una app en: https://developer.spotify.com/dashboard
#
# IMPORTANTE: Spotify NO permite reproducir audio directamente.
# Estas credenciales se usan SOLO para leer metadatos (nombre de canción,
# artista, canciones de una playlist). La reproducción siempre se hace
# desde YouTube usando yt-dlp.
# ---------------------------------------------------------------------------

SPOTIFY_CLIENT_ID: str     = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET: str = os.getenv("SPOTIFY_CLIENT_SECRET", "")

# ---------------------------------------------------------------------------
# Paleta de Colores para Embeds (formato hexadecimal)
# ---------------------------------------------------------------------------
# Kutral significa "fuego" en mapudungún → identidad visual cálida

COLOR_PRIMARY: int = 0xE25822   # Naranja fuego  — acciones generales
COLOR_SUCCESS: int = 0x2ECC71   # Verde esmeralda — operación exitosa
COLOR_ERROR:   int = 0xE74C3C   # Rojo cinabrio   — errores o rechazos
COLOR_WARNING: int = 0xF39C12   # Ámbar           — advertencias
COLOR_INFO:    int = 0x3498DB   # Azul claro       — información neutral
COLOR_MUSIC:   int = 0x9B59B6   # Púrpura          — módulo de música

# ---------------------------------------------------------------------------
# Configuración de Música
# ---------------------------------------------------------------------------

# Volumen predeterminado del reproductor (0–100)
MUSIC_DEFAULT_VOLUME: int = int(os.getenv("MUSIC_DEFAULT_VOLUME", "50"))

# Máximo de canciones permitidas en la cola por servidor
MUSIC_QUEUE_MAX_SIZE: int = 50

# ---------------------------------------------------------------------------
# Configuración de Moderación
# ---------------------------------------------------------------------------

# Cantidad máxima de mensajes que puede borrar /clear de una sola vez
MODERATION_MAX_CLEAR: int = 100

# ---------------------------------------------------------------------------
# Rutas de Persistencia (SQLite)
# ---------------------------------------------------------------------------

# Directorio donde se almacenará la base de datos local
DB_PATH: str = os.path.join(os.path.dirname(__file__), "data", "kutral.db")

# ---------------------------------------------------------------------------
# Validación al arrancar
# ---------------------------------------------------------------------------

def validate_config() -> None:
    """
    Verifica que las variables críticas de entorno estén definidas.
    Se llama en main.py antes de iniciar el bot.

    Raises:
        SystemExit: Si falta TOKEN o OWNER_ID.
    """
    errors = []

    if not TOKEN:
        errors.append("DISCORD_TOKEN no está definido en .env")
    if OWNER_ID == 0:
        errors.append("OWNER_ID no está definido en .env")
    if not AI_API_KEY:
        print("[CONFIG WARN] AI_API_KEY no esta definido -> el modulo de IA no funcionara.")
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        print("[CONFIG WARN] Credenciales de Spotify no definidas -> links de Spotify no funcionaran.")

    if errors:
        for msg in errors:
            print(f"[CONFIG ERROR] {msg}")
        raise SystemExit("Corrige los errores de configuración antes de iniciar el bot.")

<h1 align="center">Kutral Bot 🔥</h1>

<p align="center">
  Un bot de Discord multifuncional construido con Python. Pensado para ser rápido, modular y fácil de escalar. Combina inteligencia artificial, reproducción de música y herramientas de administración en un solo lugar.
</p>

## ✨ Características

- **Asistente de IA Integrado:** Conectado a la API de Groq (Llama 3) para mantener conversaciones fluidas, rápidas y naturales directamente en tu servidor.
- **Sistema de Música Avanzado:** Reproduce audio desde YouTube y Spotify. Soporte nativo para el protocolo DAVE de Discord (E2EE), controles de cola, pausa, salto y volumen.
- **Moderación Limpia:** Comandos nativos (slash commands) para banear, expulsar, limpiar mensajes masivamente y aplicar *timeouts* nativos de Discord, con registro automático en base de datos.
- **Asistente Personal (Owner Only):** Comandos privados de notas, tareas y recordatorios que solo el dueño del bot puede utilizar.
- **Arquitectura Modular:** Basado en Cogs de `discord.py` para mantener el código ordenado y escalable.

## 🛠️ Stack Tecnológico

- **Python 3.10+**
- **[discord.py](https://github.com/Rapptz/discord.py)** - Interacción con la API de Discord.
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp) & [Spotipy](https://spotipy.readthedocs.io/)** - Manejo de streams de audio y metadatos.
- **[Groq SDK](https://console.groq.com/docs/quickstart)** - Motor de Inteligencia Artificial (Llama-3).
- **SQLite (`aiosqlite`)** - Persistencia de datos asíncrona y ligera sin dependencias externas.

## 🚀 Requisitos Previos

Antes de instalar Kutral, asegúrate de tener instalado en tu sistema:
- Python 3.10 o superior.
- [Git](https://git-scm.com/).
- [FFmpeg](https://ffmpeg.org/download.html) (Añadido a tus variables de entorno o en la misma carpeta del proyecto para que la música funcione).

## ⚙️ Instalación

1. Clona este repositorio:
   ```bash
   git clone https://github.com/AAMoralesC/Kutral.git
   cd Kutral
   ```

2. Instala las dependencias necesarias. Se recomienda utilizar un entorno virtual:
   ```bash
   python -m pip install -r requirements.txt
   ```
   *Nota: El bot requiere las librerías de voz oficiales de Discord para su correcto funcionamiento (`discord.py[voice]`, `PyNaCl`).*

3. Configura tus credenciales. Renombra el archivo `.env.example` a `.env` y completa los datos:
   ```env
   # Tokens principales
   DISCORD_TOKEN=tu_token_de_discord_aqui
   OWNER_ID=tu_id_de_usuario_en_discord
   GROQ_API_KEY=tu_api_key_de_groq

   # Spotify (Opcional, para lectura de metadatos)
   SPOTIFY_CLIENT_ID=tu_client_id
   SPOTIFY_CLIENT_SECRET=tu_client_secret
   ```

## 💻 Uso

Para encender a Kutral, simplemente ejecuta el archivo principal desde tu terminal:

```bash
python main.py
```

Al arrancar, la consola te mostrará el estado de carga de cada módulo (Cog) y confirmará la sincronización de los Slash Commands. Ya podrás ir a Discord y utilizar comandos como `/play`, `/chat_clear`, o `/ping`.

## 📁 Estructura del Código

```text
KutralDs/
├── cogs/                 # Módulos independientes del bot
│   ├── ai_chat.py        # Lógica de Groq y Llama 3
│   ├── moderation.py     # Comandos de administración
│   ├── music.py          # Lógica de yt-dlp y audio
│   └── owner.py          # Herramientas privadas del creador
├── data/                 # Base de datos SQLite
├── utils/                # Helpers, checks de permisos y embeds UI
├── config.py             # Carga de variables de entorno globales
└── main.py               # Entrypoint y setup_hook
```

## 📄 Licencia

Este proyecto es abierto y libre de usar. Siéntete libre de hacer un fork, modificar el código a tu gusto y adaptarlo a las necesidades de tu propio servidor.

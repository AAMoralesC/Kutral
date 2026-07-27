# Kutral Bot 🔥

Un bot de Discord modular, moderno y multifuncional desarrollado en Python utilizando `discord.py`. Kutral integra sistemas de moderación avanzada, gestión de servidores, y asistencia mediante Inteligencia Artificial impulsada por Groq (Llama 3).

## ✨ Características Principales

*   **Arquitectura Modular (Cogs):** Código limpio y separado por responsabilidades.
*   **Inteligencia Artificial:** Asistente conversacional rápido e inteligente integrado mediante la API de Groq (Llama 3).
*   **Moderación Avanzada:** Comandos para banear, expulsar, silenciar (timeouts) y gestionar el historial de usuarios.
*   **Base de Datos Local:** Persistencia de datos asíncrona utilizando `aiosqlite` para logs y configuraciones.
*   **Slash Commands:** Totalmente integrado con la interfaz moderna de comandos de Discord.

## 🛠️ Tecnologías Utilizadas

*   **Lenguaje:** Python 3.10+
*   **Librería Core:** `discord.py`
*   **Base de Datos:** SQLite (`aiosqlite`)
*   **Inteligencia Artificial:** SDK de `groq`

## 🚀 Instalación y Uso Local

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/tu-usuario/KutralDs.git
   cd KutralDs
   ```

2. **Instalar las dependencias:**
   ```bash
   pip install -r requirements.txt
   ```
   *(Nota: Puedes instalar `discord.py`, `python-dotenv`, `aiosqlite` y `groq` manualmente si no hay un archivo de requerimientos).*

3. **Configurar las variables de entorno:**
   * Copia el archivo `.env.example` y renómbralo a `.env`.
   * Rellena el archivo `.env` con tus tokens reales (Discord Token, ID del dueño, y Groq API Key).

4. **Ejecutar el bot:**
   ```bash
   python main.py
   ```

## 📁 Estructura del Proyecto

```text
KutralDs/
├── main.py              # Punto de entrada principal
├── config.py            # Configuraciones globales y colores
├── cogs/                # Módulos del bot
│   ├── ai_chat.py       # Asistente IA (Groq)
│   ├── moderation.py    # Comandos de moderación
│   ├── organization.py  # Gestión del servidor
│   ├── owner.py         # Comandos privados (Notas/Tareas)
│   └── music.py         # Reproductor de música (Próximamente)
├── data/                # Almacenamiento local (SQLite)
└── utils/               # Funciones auxiliares y Embeds
```

## 📜 Licencia
Este proyecto es de código abierto. Eres libre de utilizarlo y modificarlo para tus propios servidores.

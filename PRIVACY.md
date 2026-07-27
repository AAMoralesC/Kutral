# Política de Privacidad de Kutral Bot

**Última actualización:** 27 de Julio de 2026

Kutral Bot ("el Bot") es un proyecto de código abierto diseñado como herramienta de moderación, asistencia de IA y reproducción de música para Discord. Nos tomamos muy en serio tu privacidad.

## 1. Datos que recopilamos
El Bot recopila y almacena datos de forma estrictamente limitada y funcional:
- **IDs de Discord:** Almacenamos el ID numérico de los usuarios únicamente cuando reciben una advertencia (comando `/warn`) o cuando el dueño del bot crea notas y tareas personales.
- **IDs de Servidores (Guilds):** Se almacenan junto a las advertencias para relacionar la advertencia con el servidor correcto.
- **Contenido de mensajes:** El bot lee el contenido de los mensajes para interactuar con la Inteligencia Artificial (Llama 3), pero **no almacena ni graba el historial de chat** en ninguna base de datos.
- **Archivos de audio:** El bot procesa links de YouTube y Spotify temporalmente en la memoria (RAM) para transmitirlos al canal de voz. No se descargan ni se almacenan copias permanentes de la música.

## 2. Uso de la información
Toda la información guardada en la base de datos (SQLite) se aloja de manera **local** en el equipo donde el bot se está ejecutando. Los datos recopilados se utilizan EXCLUSIVAMENTE para:
- Mantener un registro de advertencias (moderación).
- Permitir al dueño del bot acceder a sus notas y tareas.

## 3. Terceros
El Bot utiliza la API de **Groq** para procesar las solicitudes de Inteligencia Artificial. Los mensajes dirigidos a la IA son procesados por Groq de acuerdo con su propia [Política de Privacidad](https://groq.com/privacy-policy/). No vendemos, alquilamos ni compartimos la información de la base de datos local con ningún tercero.

## 4. Eliminación de datos
Los administradores de cada servidor tienen el derecho y la capacidad técnica de borrar los registros usando el comando `/clearwarns`. El dueño del bot puede eliminar sus notas y tareas mediante los comandos de borrado respectivos.

## 5. Contacto
Al ser un proyecto de código abierto y autoalojado (self-hosted), el administrador principal del bot es la persona que lo está ejecutando en su máquina o servidor. Para problemas con los datos alojados, contacta al administrador del servidor de Discord donde Kutral está presente.

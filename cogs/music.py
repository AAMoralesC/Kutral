"""
cogs/music.py — Módulo de Música 🎵
=====================================
Gestiona la reproducción de audio en canales de voz de Discord.

════════════════════════════════════════════════════════════════
 ARQUITECTURA DE REPRODUCCIÓN
════════════════════════════════════════════════════════════════

  Usuario escribe /play <query o link>
         │
         ├─► Link de YouTube ──────────────────► yt-dlp extrae el audio
         │                                              │
         ├─► Link de Spotify (canción) ────────► spotipy lee metadatos
         │   (artista + título)                  └──► busca en YouTube
         │                                              │
         ├─► Link de Spotify (playlist) ────────► spotipy lee todas las canciones
         │   (N canciones)                        └──► agrega a cola, reproduce en orden
         │                                              │
         └─► Texto libre ("bohemian rhapsody") ──► yt-dlp busca en YouTube
                                                        │
                                                    FFmpeg procesa el audio
                                                        │
                                                    Discord VoiceClient
                                                    transmite al canal de voz

 IMPORTANTE sobre Spotify:
    Spotify no permite streaming de audio a terceros por sus ToS.
    Este bot SOLO usa la API de Spotify para leer metadatos
    (nombre, artista, duración, imagen de portada).
    El audio siempre se reproduce desde YouTube. El usuario
    no nota diferencia: pega un link de Spotify y funciona.

════════════════════════════════════════════════════════════════

Instalación de dependencias:
    pip install yt-dlp PyNaCl spotipy
    # FFmpeg: instalar en el sistema y agregar al PATH
    # Windows: https://ffmpeg.org/download.html
    # También disponible con: winget install ffmpeg

Comandos disponibles:
    /play <query>    — Reproduce o encola (YouTube URL, Spotify URL, o texto libre)
    /skip            — Salta la canción actual
    /stop            — Detiene la reproducción y limpia la cola
    /queue           — Muestra las canciones en espera
    /pause           — Pausa la canción actual
    /resume          — Reanuda la canción pausada
    /nowplaying      — Muestra la canción en reproducción con portada y duración
    /volume <0-100>  — Ajusta el volumen del reproductor
"""

import asyncio
from collections import deque

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.checks import guild_only
from utils.embeds import music_embed, error_embed, info_embed


# ---------------------------------------------------------------------------
# Constantes de yt-dlp
# ---------------------------------------------------------------------------

# Opciones para extraer audio con yt-dlp
# bestaudio: máxima calidad de audio disponible
# noplaylist: cuando se pasa una URL de video dentro de playlist, toma solo el video
YTDLP_OPTIONS: dict = {
    "format":          "bestaudio/best",
    "noplaylist":      True,           # Las playlists se manejan manualmente
    "quiet":           True,           # Sin output en consola
    "no_warnings":     True,
    "default_search":  "ytsearch",     # Búsqueda por texto libre en YouTube
    "source_address":  "0.0.0.0",      # Evitar problemas de IPv6
}

# Opciones para FFmpeg (codec de audio que Discord necesita)
# reconnect: reconecta si el stream de red se interrumpe
FFMPEG_OPTIONS: dict = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options":        "-vn",           # -vn = solo audio, sin video
}


# ---------------------------------------------------------------------------
# Modelo de datos: Track
# ---------------------------------------------------------------------------

class Track:
    """
    Representa una canción en la cola de reproducción.

    Attributes:
        title:      Título de la canción.
        url:        URL directa del stream de audio (obtenida por yt-dlp).
        webpage_url:URL de la página de YouTube del video.
        duration:   Duración en segundos.
        thumbnail:  URL de la miniatura/portada.
        requester:  Miembro de Discord que pidió la canción.
    """

    def __init__(
        self,
        title:       str,
        url:         str,
        webpage_url: str,
        duration:    int,
        thumbnail:   str,
        requester:   discord.Member,
    ) -> None:
        self.title       = title
        self.url         = url
        self.webpage_url = webpage_url
        self.duration    = duration
        self.thumbnail   = thumbnail
        self.requester   = requester

    @property
    def duration_str(self) -> str:
        """Convierte los segundos de duración a formato mm:ss o hh:mm:ss."""
        minutes, seconds = divmod(self.duration, 60)
        hours, minutes   = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"


# ---------------------------------------------------------------------------
# Gestor de Cola por Servidor
# ---------------------------------------------------------------------------

class MusicQueue:
    """
    Gestiona el estado de reproducción de un servidor (guild).

    Cada servidor tiene su propia instancia para permitir que el bot
    opere en múltiples servidores de forma simultánea e independiente.

    Attributes:
        guild_id:     ID del servidor al que pertenece esta cola.
        tracks:       Cola de canciones pendientes (deque para eficiencia O(1)).
        current:      Canción en reproducción actualmente (None si no hay).
        voice_client: Conexión de voz activa del bot (None si no está conectado).
        volume:       Volumen actual (0.0 a 1.0).
        loop:         Si True, repite la canción actual al terminar.
    """

    def __init__(self, guild_id: int) -> None:
        self.guild_id:     int                    = guild_id
        self.tracks:       deque[Track]           = deque(maxlen=config.MUSIC_QUEUE_MAX_SIZE)
        self.current:      Track | None           = None
        self.voice_client: discord.VoiceClient | None = None
        self.volume:       float                  = config.MUSIC_DEFAULT_VOLUME / 100
        self.loop:         bool                   = False

    @property
    def is_playing(self) -> bool:
        """True si el VoiceClient existe y está reproduciendo audio."""
        return self.voice_client is not None and self.voice_client.is_playing()

    @property
    def is_paused(self) -> bool:
        """True si hay audio cargado pero está pausado."""
        return self.voice_client is not None and self.voice_client.is_paused()

    def clear(self) -> None:
        """Vacía la cola de canciones pendientes."""
        self.tracks.clear()


# ---------------------------------------------------------------------------
# Cog Principal
# ---------------------------------------------------------------------------

class Music(commands.Cog, name="Música"):
    """
    Cog de reproducción de audio en canales de voz.

    Attributes:
        bot:    Instancia principal del bot.
        queues: Diccionario que mapea guild_id → MusicQueue.
                Un MusicQueue por servidor garantiza independencia entre servidores.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # { guild_id (int): MusicQueue }
        self.queues: dict[int, MusicQueue] = {}

    # -----------------------------------------------------------------------
    # Helpers internos
    # -----------------------------------------------------------------------

    def _get_queue(self, guild_id: int) -> MusicQueue:
        """
        Retorna la MusicQueue del servidor, creándola si no existe.

        Args:
            guild_id: ID del servidor de Discord.
        """
        if guild_id not in self.queues:
            self.queues[guild_id] = MusicQueue(guild_id)
        return self.queues[guild_id]

    async def _join_voice(
        self,
        interaction: discord.Interaction,
        queue: MusicQueue,
    ) -> bool:
        """
        Conecta el bot al canal de voz del usuario que ejecutó el comando.

        Returns:
            True si se conectó correctamente, False si el usuario no está
            en un canal de voz o si ocurrió un error de permisos.
        """
        # TODO: Verificar que interaction.user está en un canal de voz
        # TODO: Si el bot ya está en otro canal del mismo servidor, moverlo
        # TODO: guild.me.voice.channel → canal actual del bot
        # TODO: await channel.connect() y guardar en queue.voice_client
        return False

    async def _resolve_query(self, query: str) -> list[Track]:
        """
        Resuelve una query en una lista de Tracks listos para reproducir.

        El método detecta automáticamente el tipo de input:
            - URL de YouTube (video)  → 1 track
            - URL de YouTube (playlist) → N tracks
            - URL de Spotify (canción) → 1 track (buscado en YouTube)
            - URL de Spotify (playlist) → N tracks (buscados en YouTube)
            - Texto libre              → 1 track (búsqueda en YouTube)

        Args:
            query: URL o texto libre ingresado por el usuario.

        Returns:
            Lista de Track listos para encolar. Lista vacía si hay error.
        """
        # TODO: Detectar tipo de URL con urlparse o regex
        # TODO: Si es Spotify → llamar _resolve_spotify(query)
        # TODO: Si es YouTube o texto → llamar _resolve_youtube(query)
        return []

    async def _resolve_youtube(self, query: str) -> list[Track]:
        """
        Usa yt-dlp para extraer info de audio de una URL de YouTube o búsqueda.

        Para búsquedas de texto se agrega "ytsearch:" como prefijo,
        que es manejado automáticamente por YTDLP_OPTIONS.

        Args:
            query: URL de YouTube o texto de búsqueda.

        Returns:
            Lista de Track (puede ser múltiple si query es una playlist).
        """
        # TODO: Usar asyncio.get_event_loop().run_in_executor() para llamar
        #       yt-dlp en un hilo separado (es una operación bloqueante)
        # TODO: ydl.extract_info(query, download=False)
        # TODO: Construir Track con los metadatos extraídos
        return []

    async def _resolve_spotify(self, url: str) -> list[Track]:
        """
        Usa spotipy para leer metadatos de Spotify y convierte cada canción
        en una búsqueda de YouTube.

        Detecta si la URL es de una canción individual o una playlist.

        Args:
            url: URL de Spotify (track o playlist).

        Returns:
            Lista de Track donde cada uno fue buscado en YouTube.
        """
        # TODO: Inicializar spotipy con SpotifyClientCredentials
        # TODO: Detectar si url contiene "track" o "playlist"
        # TODO: Para track:    sp.track(track_id) → title + artist → _resolve_youtube()
        # TODO: Para playlist: sp.playlist_tracks(playlist_id) → iterar → _resolve_youtube()
        return []

    async def _play_next(self, guild_id: int) -> None:
        """
        Reproduce la siguiente canción de la cola del servidor.

        Este método se llama automáticamente como callback cuando una
        canción termina (after= en VoiceClient.play()).

        Si la cola está vacía, desconecta el bot del canal de voz
        después de 3 minutos de inactividad (para no ocupar el canal).

        Args:
            guild_id: ID del servidor donde debe continuar la reproducción.
        """
        # TODO: Sacar el siguiente Track de queue.tracks (deque.popleft())
        # TODO: Si loop está activo, re-encolar la canción actual
        # TODO: Crear FFmpegPCMAudio con el track.url y FFMPEG_OPTIONS
        # TODO: Aplicar volumen con PCMVolumeTransformer
        # TODO: voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(...))
        # TODO: Si la cola está vacía, programar desconexión con asyncio.sleep(180)
        pass

    # -----------------------------------------------------------------------
    # Slash Commands
    # -----------------------------------------------------------------------

    @app_commands.command(name="play", description="Reproduce o encola música de YouTube o Spotify")
    @app_commands.describe(
        query="URL de YouTube, URL de Spotify, o nombre de la canción a buscar"
    )
    @guild_only()
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        """
        Punto de entrada principal del reproductor de música.

        Acepta cualquier formato de input y delega la resolución a _resolve_query().
        Si el bot no está en un canal de voz, se une al canal del usuario.
        Si ya hay algo en reproducción, agrega a la cola.

        Args:
            interaction: Contexto de la interacción de Discord.
            query:       URL de YouTube, URL de Spotify, o texto de búsqueda.
        """
        await interaction.response.defer()   # La búsqueda puede tomar segundos

        # TODO: Llamar _join_voice(); si retorna False, terminar con error
        # TODO: Llamar _resolve_query(query) para obtener lista de tracks
        # TODO: Si lista vacía, retornar error "No se encontró la canción"
        # TODO: Agregar tracks a queue.tracks
        # TODO: Si no está reproduciendo, llamar _play_next()
        # TODO: Responder con embed music_embed mostrando qué se agregó

        await interaction.followup.send(
            embed=music_embed("Reproduciendo", f"🔍 Buscando: `{query}`\n*(Función en construcción)*")
        )

    @app_commands.command(name="skip", description="Salta la canción actual")
    @guild_only()
    async def skip(self, interaction: discord.Interaction) -> None:
        """
        Detiene la canción actual; _play_next() se ejecuta automáticamente
        como callback de VoiceClient.play().
        """
        queue = self._get_queue(interaction.guild_id)

        # TODO: Verificar que queue.is_playing antes de ejecutar
        # TODO: queue.voice_client.stop() → dispara el callback after= automáticamente

        await interaction.response.send_message(
            embed=music_embed("Skip", "⏭️ Saltando canción...\n*(Función en construcción)*"),
            ephemeral=True,
        )

    @app_commands.command(name="stop", description="Detiene la música y limpia la cola")
    @guild_only()
    async def stop(self, interaction: discord.Interaction) -> None:
        """
        Para completamente la reproducción:
            1. Vacía la cola.
            2. Detiene el VoiceClient.
            3. Desconecta el bot del canal de voz.
        """
        queue = self._get_queue(interaction.guild_id)

        # TODO: queue.clear()
        # TODO: await queue.voice_client.disconnect()
        # TODO: Eliminar queue de self.queues[guild_id]

        await interaction.response.send_message(
            embed=music_embed("Detenido", "⏹️ Cola limpiada y bot desconectado.\n*(Función en construcción)*"),
            ephemeral=True,
        )

    @app_commands.command(name="queue", description="Muestra las canciones en espera")
    @guild_only()
    async def queue_cmd(self, interaction: discord.Interaction) -> None:
        """
        Lista las canciones pendientes en la cola con su posición,
        título, duración y quien la pidió.
        """
        queue = self._get_queue(interaction.guild_id)

        # TODO: Verificar que queue.tracks no está vacía
        # TODO: Paginar si hay más de 10 canciones (usar discord.ui.View con botones)
        # TODO: Mostrar también queue.current con indicador "▶️ En reproducción"

        await interaction.response.send_message(
            embed=music_embed("Cola de Reproducción", "📋 La cola está vacía.\n*(Función en construcción)*"),
            ephemeral=True,
        )

    @app_commands.command(name="pause", description="Pausa la canción actual")
    @guild_only()
    async def pause(self, interaction: discord.Interaction) -> None:
        """Pausa el stream de audio activo. Reanudable con /resume."""
        queue = self._get_queue(interaction.guild_id)

        # TODO: if queue.is_playing: queue.voice_client.pause()

        await interaction.response.send_message(
            embed=music_embed("Pausa", "⏸️ Música pausada.\n*(Función en construcción)*"),
            ephemeral=True,
        )

    @app_commands.command(name="resume", description="Reanuda la canción pausada")
    @guild_only()
    async def resume(self, interaction: discord.Interaction) -> None:
        """Reanuda el stream de audio si estaba pausado."""
        queue = self._get_queue(interaction.guild_id)

        # TODO: if queue.is_paused: queue.voice_client.resume()

        await interaction.response.send_message(
            embed=music_embed("Reanudando", "▶️ Reanudando música.\n*(Función en construcción)*"),
            ephemeral=True,
        )

    @app_commands.command(name="nowplaying", description="Muestra la canción en reproducción")
    @guild_only()
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        """
        Muestra un embed rico con:
            - Portada de la canción (thumbnail)
            - Título con link a YouTube
            - Duración total
            - Quién la pidió
        """
        queue = self._get_queue(interaction.guild_id)

        # TODO: Verificar que queue.current no es None
        # TODO: Construir embed con queue.current.thumbnail como imagen
        # TODO: Mostrar queue.current.duration_str

        await interaction.response.send_message(
            embed=music_embed("En reproducción", "🎶 Nada sonando ahora.\n*(Función en construcción)*"),
            ephemeral=True,
        )

    @app_commands.command(name="volume", description="Ajusta el volumen del reproductor (0-100)")
    @app_commands.describe(level="Nivel de volumen entre 0 y 100")
    @guild_only()
    async def volume(self, interaction: discord.Interaction, level: int) -> None:
        """
        Cambia el volumen en tiempo real sin interrumpir la reproducción.
        PCMVolumeTransformer permite ajustar el volumen dinámicamente.

        Args:
            level: Nivel de volumen deseado (0 = silencio, 100 = máximo).
        """
        queue = self._get_queue(interaction.guild_id)

        # TODO: Validar que level está entre 0 y 100
        # TODO: queue.volume = level / 100
        # TODO: Si hay un VoiceClient.source (PCMVolumeTransformer), actualizar .volume

        await interaction.response.send_message(
            embed=music_embed("Volumen", f"🔊 Volumen ajustado a **{level}%**.\n*(Función en construcción)*"),
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# Setup — Requerido por discord.py para cargar el cog
# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot) -> None:
    """Registra el cog Music en el bot."""
    await bot.add_cog(Music(bot))

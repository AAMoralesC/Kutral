"""
cogs/music.py
=====================================
Gestiona la reproduccion de audio en canales de voz de Discord.
"""

import os
import shutil
import asyncio
import aiohttp
import urllib.parse
from collections import deque

import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

import config
from utils.checks import guild_only
from utils.embeds import music_embed, error_embed, info_embed

# ---------------------------------------------------------------------------
# Dependencias y Rutas
# ---------------------------------------------------------------------------

FFMPEG_EXECUTABLE = shutil.which("ffmpeg")
if not FFMPEG_EXECUTABLE:
    fallback_path = r"C:\Users\LENOVO\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe"
    if os.path.exists(fallback_path):
        FFMPEG_EXECUTABLE = fallback_path
    else:
        FFMPEG_EXECUTABLE = "ffmpeg"

YTDLP_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "socket_timeout": 15,
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


# ---------------------------------------------------------------------------
# Modelos de Datos
# ---------------------------------------------------------------------------

class Track:
    def __init__(self, title: str, url: str, webpage_url: str, duration: int, thumbnail: str, requester: discord.Member):
        self.title = title
        self.url = url
        self.webpage_url = webpage_url
        self.duration = duration
        self.thumbnail = thumbnail
        self.requester = requester

    @property
    def duration_str(self) -> str:
        minutes, seconds = divmod(self.duration, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"


class MusicQueue:
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.tracks: deque[Track] = deque(maxlen=config.MUSIC_QUEUE_MAX_SIZE)
        self.current: Track | None = None
        self.voice_client: discord.VoiceClient | None = None
        self.text_channel = None
        self.player_message: discord.Message | None = None
        self.volume: float = config.MUSIC_DEFAULT_VOLUME / 100
        self.loop: bool = False

    @property
    def is_playing(self) -> bool:
        return self.voice_client is not None and self.voice_client.is_playing()

    @property
    def is_paused(self) -> bool:
        return self.voice_client is not None and self.voice_client.is_paused()

    def clear(self) -> None:
        self.tracks.clear()


class MusicControlView(discord.ui.View):
    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.primary, custom_id="music_pause")
    async def toggle_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = self.cog._get_queue(self.guild_id)
        if queue.voice_client:
            if queue.is_playing:
                queue.voice_client.pause()
                await interaction.response.send_message("⏸️ Música pausada.", ephemeral=True)
            elif queue.is_paused:
                queue.voice_client.resume()
                await interaction.response.send_message("▶️ Música reanudada.", ephemeral=True)
            else:
                await interaction.response.send_message("No hay música activa.", ephemeral=True)
        else:
            await interaction.response.send_message("El bot no está en un canal.", ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="music_skip")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = self.cog._get_queue(self.guild_id)
        if queue.is_playing or queue.is_paused:
            queue.voice_client.stop()
            await interaction.response.send_message("⏭️ Canción saltada.", ephemeral=True)
        else:
            await interaction.response.send_message("No hay música activa para saltar.", ephemeral=True)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="music_stop")
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = self.cog._get_queue(self.guild_id)
        queue.clear()
        if queue.voice_client:
            queue.voice_client.stop()
            await queue.voice_client.disconnect()
            queue.voice_client = None
        await interaction.response.send_message("⏹️ Reproductor detenido.", ephemeral=True)

    @discord.ui.button(emoji="📜", style=discord.ButtonStyle.secondary, custom_id="music_queue")
    async def show_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = self.cog._get_queue(self.guild_id)
        if not queue.tracks:
            await interaction.response.send_message("La cola está vacía.", ephemeral=True)
            return
        
        q_list = "\n".join(f"{i+1}. {t.title}" for i, t in enumerate(list(queue.tracks)[:10]))
        if len(queue.tracks) > 10:
            q_list += f"\n...y {len(queue.tracks) - 10} más."
        
        embed = discord.Embed(title="Cola de Reproducción", description=q_list, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Cog Principal
# ---------------------------------------------------------------------------

class Music(commands.Cog, name="Musica"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.queues: dict[int, MusicQueue] = {}
        
        # Spotipy Init
        self.sp = None
        if config.SPOTIFY_CLIENT_ID and config.SPOTIFY_CLIENT_SECRET:
            try:
                auth_manager = SpotifyClientCredentials(
                    client_id=config.SPOTIFY_CLIENT_ID,
                    client_secret=config.SPOTIFY_CLIENT_SECRET
                )
                self.sp = spotipy.Spotify(auth_manager=auth_manager)
            except Exception as e:
                print(f"[Music] Error iniciando Spotify: {e}")

        # YTMusic Init
        try:
            import ytmusicapi
            self.ytm = ytmusicapi.YTMusic()
        except ImportError:
            self.ytm = None

    def _get_queue(self, guild_id: int) -> MusicQueue:
        if guild_id not in self.queues:
            self.queues[guild_id] = MusicQueue(guild_id)
        return self.queues[guild_id]

    async def update_player_message(self, guild_id: int):
        queue = self._get_queue(guild_id)
        if not queue.text_channel:
            return
            
        if not queue.current:
            embed = discord.Embed(
                title="⏹️ Reproductor Detenido", 
                description="La cola está vacía.", 
                color=discord.Color.red()
            )
            if queue.player_message:
                try:
                    await queue.player_message.edit(embed=embed, view=None)
                except Exception:
                    pass
            return
            
        embed = music_embed("🎶 Reproduciendo Ahora", f"[{queue.current.title}]({queue.current.webpage_url})")
        if queue.current.thumbnail:
            embed.set_thumbnail(url=queue.current.thumbnail)
            
        if queue.tracks:
            q_list = "\n".join(f"{i+1}. {t.title}" for i, t in enumerate(list(queue.tracks)[:5]))
            if len(queue.tracks) > 5:
                q_list += f"\n*...y {len(queue.tracks) - 5} más*"
            embed.add_field(name="Siguientes en cola", value=q_list, inline=False)
            
        view = MusicControlView(self, guild_id)
        
        # Eliminar el panel viejo para que el nuevo quede al fondo del chat
        if queue.player_message:
            try:
                await queue.player_message.delete()
            except Exception:
                pass
                
        try:
            queue.player_message = await queue.text_channel.send(embed=embed, view=view)
        except Exception:
            pass

    async def _join_voice(self, user_or_interaction, queue: MusicQueue) -> bool:
        member = getattr(user_or_interaction, "user", user_or_interaction)
        guild = getattr(user_or_interaction, "guild", member.guild)
        
        if not member.voice or not member.voice.channel:
            return False
            
        channel = member.voice.channel
        
        if not queue.voice_client:
            try:
                queue.voice_client = await channel.connect(timeout=10.0, self_deaf=True)
            except discord.ClientException:
                queue.voice_client = guild.voice_client
            except asyncio.TimeoutError:
                return False
            except Exception:
                return False
        elif queue.voice_client.channel != channel:
            await queue.voice_client.move_to(channel)
            
        return True

    async def _resolve_query(self, query: str, requester: discord.Member) -> list[Track]:
        if "spotify.com" in query and self.sp is not None:
            return await self._resolve_spotify(query, requester)
        else:
            return await self._resolve_youtube(query, requester)

    async def _resolve_youtube(self, query: str, requester: discord.Member) -> list[Track]:
        loop = asyncio.get_event_loop()
        
        def extract():
            with yt_dlp.YoutubeDL(YTDLP_OPTIONS) as ydl:
                return ydl.extract_info(query, download=False)
                
        try:
            data = await loop.run_in_executor(None, extract)
        except Exception as e:
            print(f"[Music] yt-dlp error: {e}")
            return []

        if not data:
            return []

        tracks = []
        if "entries" in data:
            # Es una playlist o un search con varios resultados (tomamos el primero)
            for entry in data["entries"]:
                if entry:
                    tracks.append(self._create_track_from_data(entry, requester))
                if "ytsearch" in YTDLP_OPTIONS["default_search"] and not query.startswith("http"):
                    break # Solo el primer resultado si es busqueda de texto
        else:
            tracks.append(self._create_track_from_data(data, requester))

        return tracks
        
    def _create_track_from_data(self, data: dict, requester: discord.Member) -> Track:
        return Track(
            title=data.get("title", "Desconocido"),
            url=data.get("url", ""),
            webpage_url=data.get("webpage_url", ""),
            duration=data.get("duration", 0),
            thumbnail=data.get("thumbnail", ""),
            requester=requester
        )

    async def _resolve_spotify(self, url: str, requester: discord.Member) -> list[Track]:
        tracks = []
        try:
            if "track" in url:
                data = self.sp.track(url)
                search_query = f"{data['name']} {data['artists'][0]['name']}"
                tracks = await self._resolve_youtube(search_query, requester)
            elif "playlist" in url:
                data = self.sp.playlist_tracks(url)
                for item in data['items']:
                    track = item['track']
                    if track:
                        search_query = f"{track['name']} {track['artists'][0]['name']}"
                        found = await self._resolve_youtube(search_query, requester)
                        if found:
                            tracks.extend(found)
        except Exception as e:
            print(f"[Music] Spotify error: {e}")
        return tracks

    def _play_next(self, guild_id: int) -> None:
        queue = self._get_queue(guild_id)
        
        if queue.loop and queue.current:
            queue.tracks.appendleft(queue.current)
            
        if not queue.tracks:
            queue.current = None
            asyncio.run_coroutine_threadsafe(self.update_player_message(guild_id), self.bot.loop)
            asyncio.run_coroutine_threadsafe(self._disconnect_idle(guild_id), self.bot.loop)
            return
            
        queue.current = queue.tracks.popleft()
        
        try:
            source = discord.FFmpegPCMAudio(
                queue.current.url, 
                executable=FFMPEG_EXECUTABLE,
                **FFMPEG_OPTIONS
            )
            source = discord.PCMVolumeTransformer(source, volume=queue.volume)
            
            queue.voice_client.play(
                source, 
                after=lambda e: self._play_next(guild_id)
            )
            asyncio.run_coroutine_threadsafe(self.update_player_message(guild_id), self.bot.loop)
        except Exception as e:
            print(f"[Music] Error al reproducir: {e}")
            self._play_next(guild_id)

    async def _disconnect_idle(self, guild_id: int):
        await asyncio.sleep(180)
        queue = self._get_queue(guild_id)
        if not queue.is_playing and not queue.is_paused and queue.voice_client:
            await queue.voice_client.disconnect()
            queue.voice_client = None

    # -----------------------------------------------------------------------
    # Slash Commands
    # -----------------------------------------------------------------------

    async def play_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if not current:
            return []
            
        if hasattr(self, 'ytm') and self.ytm is not None:
            try:
                # ytmusicapi es síncrono, se ejecuta en executor para no bloquear el bot
                results = await self.bot.loop.run_in_executor(
                    None, lambda: self.ytm.search(current, filter="songs", limit=15)
                )
                choices = []
                seen = set()
                for item in results:
                    title = item.get("title", "")
                    artists_list = item.get("artists", [])
                    artists = ", ".join([a.get("name", "") for a in artists_list if isinstance(a, dict)])
                    name = f"{title} - {artists}" if artists else title
                    if name not in seen and len(name) > 3:
                        seen.add(name)
                        choices.append(app_commands.Choice(name=name[:100], value=name[:100]))
                
                if choices:
                    return choices[:25]
            except Exception:
                pass
            
        return [app_commands.Choice(name=current[:100], value=current[:100])]


    @app_commands.command(name="play", description="Reproduce o encola musica de YouTube o Spotify")
    @app_commands.describe(query="URL de YouTube, Spotify o texto")
    @app_commands.autocomplete(query=play_autocomplete)
    @guild_only()
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer()
        
        queue = self._get_queue(interaction.guild_id)
        queue.text_channel = interaction.channel
        
        joined = await self._join_voice(interaction, queue)
        if not joined:
            await interaction.followup.send(
                embed=error_embed("Error", "Debes estar en un canal de voz.")
            )
            return
            
        tracks = await self._resolve_query(query, interaction.user)
        if not tracks:
            await interaction.followup.send(
                embed=error_embed("Error", "No se encontro la cancion.")
            )
            return
            
        for track in tracks:
            queue.tracks.append(track)
            
        if not queue.is_playing and not queue.is_paused:
            self._play_next(interaction.guild_id)
            if len(tracks) == 1:
                await interaction.followup.send(f"✅ **{tracks[0].title}** añadido.", ephemeral=True)
            else:
                await interaction.followup.send(f"✅ Playlist de **{len(tracks)}** canciones añadida.", ephemeral=True)
        else:
            if len(tracks) == 1:
                await interaction.followup.send(f"✅ **{tracks[0].title}** añadido a la cola.", ephemeral=True)
            else:
                await interaction.followup.send(f"✅ Playlist de **{len(tracks)}** canciones añadida a la cola.", ephemeral=True)
            await self.update_player_message(interaction.guild_id)

    @app_commands.command(name="skip", description="Salta la cancion actual")
    @guild_only()
    async def skip(self, interaction: discord.Interaction) -> None:
        queue = self._get_queue(interaction.guild_id)
        if queue.is_playing or queue.is_paused:
            queue.voice_client.stop()
            await interaction.response.send_message(
                embed=music_embed("Skip", "Saltando cancion..."),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=error_embed("Error", "No hay nada sonando."),
                ephemeral=True,
            )

    @app_commands.command(name="stop", description="Detiene la musica y limpia la cola")
    @guild_only()
    async def stop(self, interaction: discord.Interaction) -> None:
        queue = self._get_queue(interaction.guild_id)
        queue.clear()
        if queue.voice_client:
            await queue.voice_client.disconnect()
            queue.voice_client = None
            
        await interaction.response.send_message(
            embed=music_embed("Detenido", "Cola limpiada y bot desconectado."),
            ephemeral=True,
        )

    @app_commands.command(name="queue", description="Muestra las canciones en espera")
    @guild_only()
    async def queue_cmd(self, interaction: discord.Interaction) -> None:
        queue = self._get_queue(interaction.guild_id)
        
        if not queue.tracks and not queue.current:
            await interaction.response.send_message(
                embed=music_embed("Cola de Reproduccion", "La cola esta vacia."),
                ephemeral=True,
            )
            return
            
        desc = ""
        if queue.current:
            desc += f"**[Sonando]** {queue.current.title} ({queue.current.duration_str})\n\n"
            
        for i, track in enumerate(list(queue.tracks)[:10], 1):
            desc += f"**{i}.** {track.title} ({track.duration_str})\n"
            
        if len(queue.tracks) > 10:
            desc += f"\n... y {len(queue.tracks) - 10} mas."
            
        await interaction.response.send_message(
            embed=music_embed("Cola de Reproduccion", desc),
            ephemeral=True,
        )

    @app_commands.command(name="pause", description="Pausa la cancion actual")
    @guild_only()
    async def pause(self, interaction: discord.Interaction) -> None:
        queue = self._get_queue(interaction.guild_id)
        if queue.is_playing:
            queue.voice_client.pause()
            await interaction.response.send_message(
                embed=music_embed("Pausa", "Musica pausada."),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=error_embed("Error", "No hay musica sonando para pausar."),
                ephemeral=True,
            )

    @app_commands.command(name="resume", description="Reanuda la cancion pausada")
    @guild_only()
    async def resume(self, interaction: discord.Interaction) -> None:
        queue = self._get_queue(interaction.guild_id)
        if queue.is_paused:
            queue.voice_client.resume()
            await interaction.response.send_message(
                embed=music_embed("Reanudando", "Reanudando musica."),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=error_embed("Error", "La musica no esta pausada."),
                ephemeral=True,
            )

    @app_commands.command(name="nowplaying", description="Muestra la cancion en reproduccion")
    @guild_only()
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        queue = self._get_queue(interaction.guild_id)
        if not queue.current:
            await interaction.response.send_message(
                embed=music_embed("En reproduccion", "Nada sonando ahora."),
                ephemeral=True,
            )
            return
            
        embed = music_embed("En reproduccion", f"[{queue.current.title}]({queue.current.webpage_url})")
        embed.add_field(name="Duracion", value=queue.current.duration_str)
        embed.add_field(name="Solicitada por", value=queue.current.requester.display_name)
        if queue.current.thumbnail:
            embed.set_thumbnail(url=queue.current.thumbnail)
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="volume", description="Ajusta el volumen (0-100)")
    @app_commands.describe(level="Nivel de volumen")
    @guild_only()
    async def volume(self, interaction: discord.Interaction, level: int) -> None:
        if not 0 <= level <= 100:
            await interaction.response.send_message(
                embed=error_embed("Error", "El volumen debe estar entre 0 y 100."),
                ephemeral=True
            )
            return
            
        queue = self._get_queue(interaction.guild_id)
        queue.volume = level / 100
        
        if queue.voice_client and queue.voice_client.source:
            queue.voice_client.source.volume = queue.volume
            
        await interaction.response.send_message(
            embed=music_embed("Volumen", f"Volumen ajustado a {level}%."),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))

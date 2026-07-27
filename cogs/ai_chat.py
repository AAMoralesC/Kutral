"""
cogs/ai_chat.py — Módulo de IA Pública 🤖
==========================================
Permite a cualquier miembro del servidor hacer consultas a la IA (Groq)
directamente desde Discord mediante comandos Slash.

Proveedor: Groq (configurado en .env)
    AI_PROVIDER = groq
    AI_API_KEY  = tu_groq_api_key
    AI_MODEL    = llama-3.3-70b-versatile

Instalación:
    pip install groq

Comandos disponibles:
    /ask <prompt>  — Envía una pregunta a la IA y recibe la respuesta
    /resetcontext  — Borra el historial de conversación actual

Eventos manejados:
    on_message     — Responde cuando se menciona al bot en un canal.

Notas de diseño:
    - Se usa interaction.response.defer() porque la IA puede tardar
      más de 3 segundos (límite de Discord antes de timeout).
    - Las respuestas largas se truncan a 4000 caracteres para no
      superar el límite de un embed de Discord.
    - Se mantiene un historial de conversación POR USUARIO en memoria
      para que la IA recuerde el contexto dentro de la misma sesión.
"""

import os
import textwrap
import asyncio
import json

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.checks import guild_only
from utils.embeds import info_embed, error_embed, primary_embed

# Límite de caracteres del description de un embed de Discord
EMBED_MAX_CHARS = 4000

# Máximo de turnos de historial a mantener por usuario (para no crecer infinito)
MAX_HISTORY_TURNS = 10


class AIChat(commands.Cog, name="IA Pública"):
    """
    Cog de integración con Groq (Llama 3, Mixtral, etc.).

    Attributes:
        bot     : Instancia principal del bot.
        client  : Instancia del cliente asíncrono de Groq (None si hay error).
        history : Historial de conversación por usuario.
                  { user_id (int): lista de mensajes en formato OpenAI/Groq }
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot    = bot
        self.client = self._setup_groq()
        # { user_id: [{"role": "user"|"assistant", "content": "texto"}, ...] }
        self.history: dict[int, list[dict]] = {}

    # -----------------------------------------------------------------------
    # Inicialización del cliente de Groq
    # -----------------------------------------------------------------------

    def _setup_groq(self):
        """
        Configura e instancia el cliente asíncrono de Groq.

        Returns:
            groq.AsyncGroq listo para usar, o None si hay error.
        """
        if not config.AI_API_KEY:
            print("  ⚠️  [AIChat] AI_API_KEY no definida — módulo de IA desactivado.")
            return None

        try:
            from groq import AsyncGroq

            client = AsyncGroq(api_key=config.AI_API_KEY)
            print(f"  ✅ [AIChat] Groq inicializado con modelo: {config.AI_MODEL}")
            return client

        except ImportError:
            print("  ❌ [AIChat] 'groq' no instalado. Ejecuta: pip install groq")
            return None
        except Exception as e:
            print(f"  ❌ [AIChat] Error al inicializar Groq: {e}")
            return None

    # -----------------------------------------------------------------------
    # Helpers internos
    # -----------------------------------------------------------------------

    def _get_history(self, user_id: int) -> list[dict]:
        """
        Retorna el historial de conversación de un usuario con el system prompt.
        Si no existe, lo inicializa.
        """
        if user_id not in self.history:
            system_instruction = (
                "Eres Kutral, un asistente de IA integrado en un servidor de Discord. "
                "Tu nombre significa 'fuego' en mapudungún. "
                "Eres amigable, conciso y útil. Responde siempre en el mismo idioma "
                "que el usuario. Si la pregunta es inapropiada o dañina, recházala "
                "con educación. No uses markdown excesivo."
            )
            self.history[user_id] = [{"role": "system", "content": system_instruction}]
            
        return self.history[user_id]

    def _add_to_history(self, user_id: int, role: str, text: str) -> None:
        """
        Agrega un turno al historial y lo trunca si supera MAX_HISTORY_TURNS.
        El system prompt original siempre se conserva.
        """
        history = self._get_history(user_id)
        history.append({"role": role, "content": text})

        # Calcular longitud (excluyendo el system prompt inicial)
        if len(history) > (MAX_HISTORY_TURNS * 2) + 1:
            # Mantener system prompt en índice 0, y luego los últimos turnos
            self.history[user_id] = [history[0]] + history[-(MAX_HISTORY_TURNS * 2):]

    async def _ask_groq(self, member: discord.Member, channel: discord.TextChannel, prompt: str) -> str:
        """
        Envía el prompt a Groq incluyendo el historial de conversación.
        Soporta uso de herramientas (Tool Calling).
        """
        user_id = member.id
        history = self._get_history(user_id)
        
        messages = list(history)
        
        is_boss = (user_id == config.OWNER_ID)
        boss_text = "Él es tu dueño y creador, llámale 'jefe' o 'amo'." if is_boss else f"Estás hablando con {member.display_name}."
        dynamic_system = f"Contexto actual: {boss_text}. Tienes herramientas de música. Úsalas de forma autónoma si el usuario te pide reproducir, pausar, saltar o detener música. Al usar una herramienta, avisa al usuario que lo estás haciendo de forma entretenida y amigable."
        messages.append({"role": "system", "content": dynamic_system})
        messages.append({"role": "user", "content": prompt})

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "reproducir_musica",
                    "description": "Reproduce o encola una canción de YouTube.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "El nombre de la canción o artista a buscar."}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "saltar_cancion",
                    "description": "Salta la canción que está sonando actualmente."
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "pausar_musica",
                    "description": "Pausa la música actual."
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "detener_musica",
                    "description": "Detiene la música y limpia la cola."
                }
            }
        ]

        chat_completion = await self.client.chat.completions.create(
            messages=messages,
            model=config.AI_MODEL,
            temperature=0.7,
            max_tokens=2048,
            tools=tools,
            tool_choice="auto"
        )
        
        response_message = chat_completion.choices[0].message
        
        if response_message.tool_calls:
            messages.append(response_message)
            music_cog = self.bot.get_cog("Musica")
            
            for tool_call in response_message.tool_calls:
                func_name = tool_call.function.name
                result_str = "Error: Herramienta no encontrada."
                
                if music_cog:
                    try:
                        queue = music_cog._get_queue(member.guild.id)
                        queue.text_channel = channel
                        
                        if func_name == "reproducir_musica":
                            args = json.loads(tool_call.function.arguments)
                            query = args.get("query")
                            joined = await music_cog._join_voice(member, queue)
                            if not joined:
                                result_str = "Error: El usuario no está en un canal de voz."
                            else:
                                tracks = await music_cog._resolve_query(query, member)
                                if tracks:
                                    for t in tracks:
                                        queue.tracks.append(t)
                                    if not queue.is_playing and not queue.is_paused:
                                        music_cog._play_next(member.guild.id)
                                    else:
                                        await music_cog.update_player_message(member.guild.id)
                                    result_str = f"Éxito: Se añadió '{tracks[0].title}' a la cola."
                                else:
                                    result_str = "Error: No se encontraron resultados."
                                    
                        elif func_name == "saltar_cancion":
                            if queue.is_playing or queue.is_paused:
                                queue.voice_client.stop()
                                result_str = "Éxito: Canción saltada."
                            else:
                                result_str = "Error: No hay música sonando."
                                
                        elif func_name == "pausar_musica":
                            if queue.is_playing:
                                queue.voice_client.pause()
                                result_str = "Éxito: Música pausada."
                            else:
                                result_str = "Error: No hay música reproduciéndose."
                                
                        elif func_name == "detener_musica":
                            queue.clear()
                            if queue.is_playing or queue.is_paused:
                                queue.voice_client.stop()
                            await music_cog.update_player_message(member.guild.id)
                            result_str = "Éxito: Música detenida."
                            
                    except Exception as e:
                        result_str = f"Error interno: {e}"
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": func_name,
                    "content": result_str
                })
                
            chat_completion = await self.client.chat.completions.create(
                messages=messages,
                model=config.AI_MODEL,
                temperature=0.7,
                max_tokens=2048,
            )
            answer = chat_completion.choices[0].message.content
        else:
            answer = response_message.content

        self._add_to_history(user_id, "user", prompt)
        self._add_to_history(user_id, "assistant", answer)

        return answer

    def _truncate(self, text: str, max_chars: int = EMBED_MAX_CHARS) -> str:
        """Trunca el texto al límite del embed de Discord."""
        if len(text) <= max_chars:
            return text
        suffix  = "\n\n*[Respuesta truncada — usa /ask con una pregunta más específica]*"
        return text[:max_chars - len(suffix)] + suffix

    # -----------------------------------------------------------------------
    # Slash Commands
    # -----------------------------------------------------------------------

    @app_commands.command(name="ask", description="Haz una pregunta a Kutral IA")
    @app_commands.describe(prompt="Tu pregunta o instrucción para la IA")
    @guild_only()
    async def ask(self, interaction: discord.Interaction, prompt: str) -> None:
        """Envía el prompt a Groq y devuelve la respuesta en un embed."""
        if self.client is None:
            await interaction.response.send_message(
                embed=error_embed("IA no disponible", "Módulo no configurado."),
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        try:
            answer = await self._ask_groq(interaction.user, interaction.channel, prompt)
        except Exception as e:
            await interaction.followup.send(
                embed=error_embed("Error de la IA", f"No pude procesar tu solicitud: `{e}`")
            )
            return

        embed = discord.Embed(
            color=config.COLOR_INFO,
            description=self._truncate(answer),
        )
        embed.set_author(
            name=f"Pregunta de {interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url,
        )
        embed.add_field(name="📝 Prompt", value=f"> {textwrap.shorten(prompt, width=200, placeholder='...')}", inline=False)
        embed.set_footer(text=f"Kutral IA • {config.AI_MODEL}")

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="resetcontext", description="Borra el historial de conversación con la IA")
    @guild_only()
    async def resetcontext(self, interaction: discord.Interaction) -> None:
        """Limpia el historial de conversación del usuario con la IA."""
        if interaction.user.id in self.history:
            del self.history[interaction.user.id]

        await interaction.response.send_message(
            embed=info_embed(
                "Contexto reiniciado",
                "🧹 Tu historial de conversación con la IA fue borrado.",
            ),
            ephemeral=True,
        )

    # -----------------------------------------------------------------------
    # Evento de mención
    # -----------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Responde automáticamente cuando se menciona al bot."""
        if message.author.bot or self.bot.user not in message.mentions or self.client is None:
            return

        prompt = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
        if not prompt:
            await message.reply("¡Hola! ¿En qué te puedo ayudar? Escribe tu pregunta.")
            return

        async with message.channel.typing():
            try:
                answer = await self._ask_groq(message.author, message.channel, prompt)
                await message.reply(self._truncate(answer, 1900))
            except Exception as e:
                await message.reply(f"❌ Error al consultar la IA: `{e}`")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AIChat(bot))

"""
cogs/levels.py — Sistema de Niveles y Experiencia (XP)
======================================================
Módulo encargado de registrar la actividad de los usuarios y otorgar experiencia.

Características:
    - Otorga XP aleatorio por cada mensaje enviado.
    - Implementa un "cooldown" (enfriamiento) en memoria para evitar spam de XP.
    - Comandos visuales (/rank y /leaderboard) para consultar el progreso.
"""

import random
import time

import discord
from discord import app_commands
from discord.ext import commands

import config
from data import database as db
from utils.embeds import info_embed, success_embed
from utils.checks import guild_only


class Levels(commands.Cog, name="Sistema de Niveles"):
    """
    Cog que maneja la experiencia, niveles y leaderboards.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Diccionario para almacenar los cooldowns en memoria (muy rápido).
        # Estructura: { "guild_id-user_id": timestamp_del_ultimo_mensaje }
        self._cooldowns = {}
        # Segundos que deben pasar entre mensajes para volver a ganar XP
        self.COOLDOWN_SECONDS = 60

    def _is_on_cooldown(self, guild_id: int, user_id: int) -> bool:
        """Comprueba si el usuario debe esperar para ganar más XP."""
        key = f"{guild_id}-{user_id}"
        now = time.time()
        
        last_time = self._cooldowns.get(key, 0)
        if (now - last_time) < self.COOLDOWN_SECONDS:
            return True
            
        # Si no estaba en cooldown, actualizamos el tiempo de inmediato
        self._cooldowns[key] = now
        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """
        Escucha todos los mensajes en los servidores.
        Si el usuario no es un bot y no está en cooldown, le otorga XP.
        """
        # Ignorar mensajes de bots o mensajes en DMs
        if message.author.bot or message.guild is None:
            return

        guild_id = message.guild.id
        user_id = message.author.id

        # Si el usuario mandó un mensaje hace menos de 60 segundos, ignoramos
        if self._is_on_cooldown(guild_id, user_id):
            return

        # Otorga una cantidad aleatoria de XP entre 15 y 25
        xp_to_add = random.randint(15, 25)
        
        # Registrar en la base de datos
        result = await db.add_xp(guild_id, user_id, xp_to_add)

        # Si el usuario subió de nivel, enviamos un mensaje de felicitación
        if result["level_up"]:
            new_lvl = result["new_level"]
            embed = discord.Embed(
                title="¡Subida de Nivel! 🎉",
                description=f"¡Felicidades {message.author.mention}! Acabas de alcanzar el **Nivel {new_lvl}**.",
                color=config.COLOR_SUCCESS
            )
            embed.set_thumbnail(url=message.author.display_avatar.url)
            
            try:
                # Intentamos enviar el mensaje en el mismo canal
                await message.channel.send(embed=embed)
            except discord.Forbidden:
                # Si el bot no tiene permisos para hablar ahí, lo ignoramos
                pass

    @app_commands.command(name="rank", description="Muestra tu nivel y XP actual")
    @app_commands.describe(user="El usuario a consultar (opcional)")
    @guild_only()
    async def rank(self, interaction: discord.Interaction, user: discord.Member = None) -> None:
        """
        Muestra la tarjeta de nivel del usuario (o de otro si se especifica).
        """
        target = user or interaction.user
        
        if target.bot:
            await interaction.response.send_message(
                embed=info_embed("Rank", "Los bots no ganan experiencia."),
                ephemeral=True
            )
            return

        # Consultar la DB
        data = await db.get_user_level(interaction.guild_id, target.id)
        level = data["level"]
        xp = data["xp"]
        req_xp = data["xp_required_for_next"]

        # Calcular progreso para la barra
        # req_xp es lo que falta desde que el xp (restante) llegó a 0 en el nivel actual.
        progress = xp / req_xp if req_xp > 0 else 0
        bars = int(progress * 10)
        bar_str = "🟩" * bars + "⬛" * (10 - bars)
        percentage = round(progress * 100)

        embed = discord.Embed(
            title=f"Estadísticas de {target.display_name}",
            color=target.color if target.color != discord.Color.default() else config.COLOR_INFO
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Nivel", value=f"**{level}**", inline=True)
        embed.add_field(name="XP Acumulado (Nivel actual)", value=f"**{xp}** / {req_xp}", inline=True)
        embed.add_field(name="Progreso", value=f"{bar_str} **{percentage}%**", inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="Muestra el top 10 de usuarios con más nivel")
    @guild_only()
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        """
        Muestra la tabla de clasificación del servidor actual.
        """
        top_users = await db.get_leaderboard(interaction.guild_id, limit=10)

        if not top_users:
            await interaction.response.send_message(
                embed=info_embed("Leaderboard", "Todavía nadie ha ganado experiencia en este servidor.")
            )
            return

        embed = discord.Embed(
            title=f"🏆 Top 10 - {interaction.guild.name}",
            description="Los usuarios más activos del servidor:",
            color=config.COLOR_SUCCESS
        )

        for i, row in enumerate(top_users, 1):
            # Medallas para los 3 primeros
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"**{i}.**"
            
            # Buscar el usuario en el caché de Discord
            member = interaction.guild.get_member(row["user_id"])
            if member:
                name = member.display_name
            else:
                name = f"Usuario Desconocido ({row['user_id']})"

            embed.add_field(
                name=f"{medal} {name}",
                value=f"Nivel **{row['level']}** | {row['xp']} XP",
                inline=False
            )

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Registra el cog de niveles."""
    await bot.add_cog(Levels(bot))

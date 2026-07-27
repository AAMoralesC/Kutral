"""
cogs/organization.py — Módulo de Organización del Servidor 🎉
==============================================================
Gestiona la automatización de bienvenidas, despedidas y asignación
de roles al momento en que los miembros entran o salen del servidor.

Eventos manejados:
    on_member_join    — Se dispara cuando un nuevo miembro entra al servidor.
    on_member_remove  — Se dispara cuando un miembro abandona el servidor.

Comandos de configuración (solo moderadores):
    /set_welcome_channel <channel> — Define el canal donde se anuncian bienvenidas.
    /set_default_role   <role>     — Define el rol que se asigna automáticamente.
    /set_farewell_channel <channel>— Define el canal donde se anuncian despedidas.

Notas de diseño:
    La configuración (canal, rol) se persiste en SQLite por guild_id,
    permitiendo que el bot opere en múltiples servidores con ajustes propios.
    Un cache en memoria evita consultas repetidas a la DB en cada evento.
"""

import discord
from discord import app_commands
from discord.ext import commands

from data import database as db
from utils.checks import is_moderator, guild_only
from utils.embeds import success_embed, error_embed, primary_embed


class Organization(commands.Cog, name="Organización"):
    """
    Cog de automatización y organización del servidor.

    Attributes:
        bot          : Instancia principal del bot.
        guild_config : Cache en memoria de la configuración por servidor.
                       Estructura: { guild_id: {welcome_channel, default_role, farewell_channel} }
                       Se llena desde SQLite la primera vez que se necesita (lazy loading)
                       y se actualiza al cambiar la configuración.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Cache local para evitar consultas repetidas a la base de datos
        # { guild_id (int): { "welcome_channel": int|None, ... } }
        self.guild_config: dict[int, dict] = {}

    # -----------------------------------------------------------------------
    # Helpers internos
    # -----------------------------------------------------------------------

    async def _load_config(self, guild_id: int) -> dict:
        """
        Obtiene la configuración del servidor con cache.

        Primero busca en el cache en memoria; si no está,
        consulta la base de datos y guarda en cache para la próxima vez.

        Args:
            guild_id: ID del servidor de Discord.

        Returns:
            Dict con: welcome_channel, farewell_channel, default_role (int o None).
        """
        if guild_id not in self.guild_config:
            self.guild_config[guild_id] = await db.get_guild_config(guild_id)
        return self.guild_config[guild_id]

    def _build_welcome_embed(self, member: discord.Member) -> discord.Embed:
        """
        Construye el embed visual de bienvenida para un nuevo miembro.

        El embed incluye:
            - Avatar del miembro como thumbnail
            - Nombre y mención del miembro
            - Número de miembros actual del servidor

        Args:
            member: El nuevo miembro que ingresó al servidor.

        Returns:
            discord.Embed con el diseño de bienvenida de Kutral.
        """
        embed = discord.Embed(
            title=f"¡Bienvenido/a a {member.guild.name}! 🔥",
            description=(
                f"Hey {member.mention}, ¡nos alegra que estés aquí!\n\n"
                f"Eres el miembro número **{member.guild.member_count}**.\n"
                f"¡Esperamos que disfrutes tu estadía!"
            ),
            color=0xE25822,   # Naranja fuego — identidad de Kutral
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"ID: {member.id}")
        return embed

    def _build_farewell_embed(self, member: discord.Member) -> discord.Embed:
        """
        Construye el embed de despedida cuando un miembro abandona el servidor.

        Args:
            member: El miembro que salió del servidor.

        Returns:
            discord.Embed con el mensaje de despedida.
        """
        embed = discord.Embed(
            title="Alguien nos dejó... 👋",
            description=f"**{member.display_name}** ha abandonado el servidor.",
            color=0x95A5A6,   # Gris — tono neutral para despedidas
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"ID: {member.id}")
        return embed

    # -----------------------------------------------------------------------
    # Eventos de Discord
    # -----------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """
        Se dispara automáticamente cuando alguien se une al servidor.

        Acciones en orden:
            1. Cargar la configuración del servidor (cache o DB).
            2. Asignar el rol por defecto si está configurado.
            3. Enviar el embed de bienvenida al canal configurado.

        Los errores se manejan silenciosamente para no crashear el bot
        si el rol fue eliminado o el canal ya no existe.

        Args:
            member: El nuevo miembro que ingresó al servidor.
        """
        cfg = await self._load_config(member.guild.id)

        # 1. Asignar rol por defecto
        if cfg["default_role"]:
            role = member.guild.get_role(cfg["default_role"])
            if role:
                try:
                    await member.add_roles(role, reason="Rol automático al unirse")
                except discord.Forbidden:
                    # El bot no tiene permisos suficientes para asignar el rol
                    print(f"[Organization] Sin permisos para asignar rol en {member.guild.name}")
                except discord.HTTPException as e:
                    print(f"[Organization] Error al asignar rol: {e}")

        # 2. Enviar mensaje de bienvenida
        if cfg["welcome_channel"]:
            channel = member.guild.get_channel(cfg["welcome_channel"])
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    await channel.send(embed=self._build_welcome_embed(member))
                except discord.Forbidden:
                    print(f"[Organization] Sin permisos para enviar en canal de bienvenida en {member.guild.name}")
                except discord.HTTPException as e:
                    print(f"[Organization] Error al enviar bienvenida: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """
        Se dispara automáticamente cuando alguien abandona el servidor
        (ya sea voluntariamente, por kick o por ban).

        Acciones:
            1. Cargar la configuración del servidor (cache o DB).
            2. Enviar el embed de despedida al canal configurado.

        Args:
            member: El miembro que salió del servidor.
        """
        cfg = await self._load_config(member.guild.id)

        if cfg["farewell_channel"]:
            channel = member.guild.get_channel(cfg["farewell_channel"])
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    await channel.send(embed=self._build_farewell_embed(member))
                except discord.Forbidden:
                    print(f"[Organization] Sin permisos para enviar en canal de despedida en {member.guild.name}")
                except discord.HTTPException as e:
                    print(f"[Organization] Error al enviar despedida: {e}")

    # -----------------------------------------------------------------------
    # Slash Commands de Configuración
    # -----------------------------------------------------------------------

    @app_commands.command(
        name="set_welcome_channel",
        description="Configura el canal donde se anunciarán las bienvenidas",
    )
    @app_commands.describe(channel="Canal de texto donde aparecerán los mensajes de bienvenida")
    @is_moderator()
    @guild_only()
    async def set_welcome_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        """
        Guarda el canal de bienvenida en la base de datos y actualiza el cache.

        Args:
            channel: Canal de texto seleccionado por el moderador.
        """
        guild_id = interaction.guild_id

        # Persistir en la base de datos
        await db.set_guild_config(guild_id, welcome_channel=channel.id)

        # Actualizar cache para que el cambio sea inmediato sin reiniciar
        if guild_id in self.guild_config:
            self.guild_config[guild_id]["welcome_channel"] = channel.id

        await interaction.response.send_message(
            embed=success_embed(
                "Canal de bienvenidas configurado",
                f"Los nuevos miembros serán bienvenidos en {channel.mention}.",
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="set_default_role",
        description="Configura el rol que se asignará automáticamente a nuevos miembros",
    )
    @app_commands.describe(role="Rol que recibirán los nuevos miembros al entrar")
    @is_moderator()
    @guild_only()
    async def set_default_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ) -> None:
        """
        Guarda el rol por defecto en la base de datos y actualiza el cache.

        Verifica que el bot pueda asignar ese rol (jerarquía de roles):
        el rol del bot debe estar por encima del rol objetivo.

        Args:
            role: Rol de Discord a asignar automáticamente.
        """
        guild_id = interaction.guild_id

        # Verificar que el bot puede asignar este rol (jerarquía)
        bot_member = interaction.guild.me
        if role >= bot_member.top_role:
            await interaction.response.send_message(
                embed=error_embed(
                    "No puedo asignar ese rol",
                    f"El rol **{role.name}** está por encima o al mismo nivel que mi rol más alto.\n"
                    "Mueve mi rol por encima en la configuración del servidor.",
                ),
                ephemeral=True,
            )
            return

        # Persistir en la base de datos
        await db.set_guild_config(guild_id, default_role=role.id)

        # Actualizar cache
        if guild_id in self.guild_config:
            self.guild_config[guild_id]["default_role"] = role.id

        await interaction.response.send_message(
            embed=success_embed(
                "Rol automático configurado",
                f"Los nuevos miembros recibirán el rol **{role.name}** al unirse.",
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="set_farewell_channel",
        description="Configura el canal donde se anunciarán las despedidas",
    )
    @app_commands.describe(channel="Canal de texto donde aparecerán los mensajes de despedida")
    @is_moderator()
    @guild_only()
    async def set_farewell_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        """
        Guarda el canal de despedida en la base de datos y actualiza el cache.

        Args:
            channel: Canal de texto seleccionado por el moderador.
        """
        guild_id = interaction.guild_id

        # Persistir en la base de datos
        await db.set_guild_config(guild_id, farewell_channel=channel.id)

        # Actualizar cache
        if guild_id in self.guild_config:
            self.guild_config[guild_id]["farewell_channel"] = channel.id

        await interaction.response.send_message(
            embed=success_embed(
                "Canal de despedidas configurado",
                f"Las despedidas se anunciarán en {channel.mention}.",
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="server_config",
        description="Muestra la configuración actual del servidor",
    )
    @is_moderator()
    @guild_only()
    async def server_config(self, interaction: discord.Interaction) -> None:
        """
        Muestra un resumen de toda la configuración del servidor:
        canal de bienvenida, canal de despedida y rol por defecto.

        Útil para verificar que todo está configurado correctamente.
        """
        cfg = await self._load_config(interaction.guild_id)
        guild = interaction.guild

        # Resolver IDs a objetos de Discord para mostrar menciones
        welcome_ch  = guild.get_channel(cfg["welcome_channel"])  if cfg["welcome_channel"]  else None
        farewell_ch = guild.get_channel(cfg["farewell_channel"]) if cfg["farewell_channel"] else None
        def_role    = guild.get_role(cfg["default_role"])         if cfg["default_role"]    else None

        embed = discord.Embed(
            title=f"⚙️  Configuración de {guild.name}",
            color=0xE25822,
        )
        embed.add_field(
            name="📣 Canal de Bienvenidas",
            value=welcome_ch.mention  if welcome_ch  else "❌ No configurado",
            inline=False,
        )
        embed.add_field(
            name="👋 Canal de Despedidas",
            value=farewell_ch.mention if farewell_ch else "❌ No configurado",
            inline=False,
        )
        embed.add_field(
            name="🎭 Rol Automático",
            value=def_role.mention    if def_role    else "❌ No configurado",
            inline=False,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Setup — Requerido por discord.py para cargar el cog
# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot) -> None:
    """Registra el cog Organization en el bot."""
    await bot.add_cog(Organization(bot))

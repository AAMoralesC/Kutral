"""
utils/checks.py — Guardias de Permisos Personalizados
======================================================
Decoradores de verificación de permisos para usarse en los Cogs.
Centralizar los checks aquí evita duplicar lógica de autorización.

Uso:
    from utils.checks import is_owner, is_moderator

    @app_commands.command()
    @is_owner()
    async def mi_comando(self, interaction: discord.Interaction):
        ...
"""

import discord
from discord import app_commands
from discord.ext import commands

import config


# ---------------------------------------------------------------------------
# Guard: Solo el dueño del bot
# ---------------------------------------------------------------------------

def is_owner() -> app_commands.check:
    """
    Restringe un Slash Command al OWNER_ID definido en config.py.

    Si el usuario no es el dueño, Discord recibirá un error genérico
    de interacción; el handler en main.py se encargará del mensaje.
    """
    def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.id == config.OWNER_ID

    return app_commands.check(predicate)


# ---------------------------------------------------------------------------
# Guard: Solo moderadores del servidor
# ---------------------------------------------------------------------------

def is_moderator() -> app_commands.check:
    """
    Permite el comando solo a miembros con el permiso 'manage_messages'
    o con permiso de Administrador.

    Esto cubre tanto a administradores del servidor como a moderadores
    con permisos explícitos de gestión de mensajes.
    """
    def predicate(interaction: discord.Interaction) -> bool:
        # interaction.user puede ser User en DMs; comprobamos que sea Member
        if not isinstance(interaction.user, discord.Member):
            return False
        perms: discord.Permissions = interaction.user.guild_permissions
        return perms.manage_messages or perms.administrator

    return app_commands.check(predicate)


# ---------------------------------------------------------------------------
# Guard: Solo en servidores (no en DMs)
# ---------------------------------------------------------------------------

def guild_only() -> app_commands.check:
    """
    Bloquea el comando si se usa fuera de un servidor (ej. en DMs).
    Útil para comandos que requieren contexto de guild (roles, canales, etc.).
    """
    def predicate(interaction: discord.Interaction) -> bool:
        return interaction.guild is not None

    return app_commands.check(predicate)

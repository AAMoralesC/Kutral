"""
utils/embeds.py — Fábrica de Embeds Reutilizables
==================================================
Funciones helper para generar embeds de Discord con la identidad
visual de Kutral de manera consistente en todos los cogs.

Por qué centralizar embeds:
    - Garantiza uniformidad visual en todo el bot.
    - Evita repetir código de construcción de embeds en cada comando.
    - Facilita cambiar el diseño global desde un único lugar.

Uso:
    from utils.embeds import success_embed, error_embed, info_embed

    embed = success_embed("Operación completada", "El usuario fue baneado.")
    await interaction.response.send_message(embed=embed)
"""

import discord
from datetime import datetime

import config


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _base_embed(title: str, description: str, color: int) -> discord.Embed:
    """
    Construye un embed base con timestamp y footer estándar de Kutral.

    Args:
        title:       Título del embed.
        description: Cuerpo del embed.
        color:       Color lateral del embed (int hexadecimal).

    Returns:
        discord.Embed listo para enviar.
    """
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.utcnow(),
    )
    embed.set_footer(text="Kutral Bot")
    return embed


# ---------------------------------------------------------------------------
# Embeds públicos
# ---------------------------------------------------------------------------

def success_embed(title: str, description: str = "") -> discord.Embed:
    """Embed verde para confirmar una operacion exitosa."""
    return _base_embed(title, description, config.COLOR_SUCCESS)


def error_embed(title: str, description: str = "") -> discord.Embed:
    """Embed rojo para reportar errores o acciones rechazadas."""
    return _base_embed(title, description, config.COLOR_ERROR)


def warning_embed(title: str, description: str = "") -> discord.Embed:
    """Embed ambar para advertencias no criticas."""
    return _base_embed(title, description, config.COLOR_WARNING)


def info_embed(title: str, description: str = "") -> discord.Embed:
    """Embed azul para mensajes informativos neutrales."""
    return _base_embed(title, description, config.COLOR_INFO)


def music_embed(title: str, description: str = "") -> discord.Embed:
    """Embed purpura exclusivo para el modulo de musica."""
    return _base_embed(title, description, config.COLOR_MUSIC)


def primary_embed(title: str, description: str = "") -> discord.Embed:
    """Embed naranja con la identidad principal de Kutral."""
    return _base_embed(title, description, config.COLOR_PRIMARY)

"""
main.py — Punto de Entrada de Kutral Bot
=========================================
Responsabilidades de este archivo (solo estas, nada más):
    1. Validar la configuración del entorno.
    2. Definir los Intents de Discord.
    3. Inicializar el bot y cargar todos los cogs en setup_hook().
    4. Manejar el evento on_ready.
    5. Registrar un handler global de errores de interacción.
    6. Arrancar el bot con el TOKEN.

Agregar lógica de comandos aquí está PROHIBIDO.
Cada funcionalidad vive en su cog correspondiente dentro de /cogs.
"""

import asyncio
import os
import sys

# Forzar UTF-8 en la consola de Windows para evitar UnicodeEncodeError
# con caracteres especiales en los mensajes de log.
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import discord
from discord import app_commands
from discord.ext import commands

import config
from config import validate_config
from data.database import init_db


# ---------------------------------------------------------------------------
# Lista de Cogs a cargar
# ---------------------------------------------------------------------------
# Para agregar un nuevo módulo: solo añade su nombre aquí.
# El formato es "cogs.<nombre_del_archivo_sin_.py>"

COGS: list[str] = [
    "cogs.music",
    "cogs.moderation",
    "cogs.organization",
    "cogs.ai_chat",
    "cogs.owner",
]


# ---------------------------------------------------------------------------
# Clase del Bot
# ---------------------------------------------------------------------------

class KutralBot(commands.Bot):
    """
    Clase principal de Kutral.

    Extiende commands.Bot para tener control sobre el ciclo de vida,
    especialmente la carga de cogs antes de que el bot se conecte a Discord.
    """

    def __init__(self) -> None:
        # Intents: permisos que el bot necesita de Discord
        intents = discord.Intents.default()
        intents.message_content = True  # Leer contenido de mensajes (módulo IA)
        intents.members = True          # Detectar entradas/salidas de miembros (organización)

        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self) -> None:
        """
        Método del ciclo de vida de discord.py.
        Se ejecuta UNA VEZ antes de que el bot se conecte a Discord.
        Es el lugar correcto para cargar extensiones/cogs.
        """
        # Inicializar la base de datos antes de cargar los cogs
        # (los cogs pueden necesitar la DB al instanciarse)
        import os
        os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
        await init_db()

        for cog in COGS:
            try:
                await self.load_extension(cog)
                print(f"  ✅ Cog cargado: {cog}")
            except Exception as e:
                # Un cog fallido no detiene el arranque del bot;
                # se registra el error para diagnóstico.
                print(f"  ❌ Error al cargar {cog}: {e}")

    async def on_ready(self) -> None:
        """
        Se ejecuta cuando el bot está completamente conectado y listo.
        Sincroniza los Slash Commands con la API de Discord.
        """
        print(f"\n{'='*45}")
        print(f"  Kutral está en línea 🔥")
        print(f"  Conectado como: {self.user} (ID: {self.user.id})")
        print(f"{'='*45}\n")

        try:
            synced = await self.tree.sync()
            print(f"  Slash Commands sincronizados: {len(synced)}\n")
        except Exception as e:
            print(f"  Error al sincronizar Slash Commands: {e}\n")

    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """
        Handler global para errores de interacción (permisos denegados, etc.).
        Intercepta los errores de los checks (@is_owner, @is_moderator)
        y envía un mensaje claro al usuario en lugar del error genérico de Discord.
        """
        # Este método solo maneja el flujo normal de interacciones.
        # Los errores de los app_commands se capturan en on_app_command_error.
        await super().on_interaction(interaction)

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """
        Handler global de errores para todos los Slash Commands.

        Captura errores comunes y responde al usuario con mensajes descriptivos.
        Los errores no manejados se imprimen en consola para diagnóstico.

        Args:
            interaction: Contexto donde ocurrió el error.
            error:       Excepción capturada por el framework.
        """
        from utils.embeds import error_embed

        if isinstance(error, app_commands.CheckFailure):
            # El usuario no cumplió con alguno de los guards (is_owner, is_moderator, etc.)
            await interaction.response.send_message(
                embed=error_embed(
                    "Sin permisos",
                    "No tienes los permisos necesarios para usar este comando.",
                ),
                ephemeral=True,
            )
        else:
            # Error inesperado: notificar al usuario y loggear para el desarrollador
            print(f"[ERROR] Comando: /{interaction.command.name if interaction.command else '?'}")
            print(f"        Tipo: {type(error).__name__}")
            print(f"        Detalle: {error}")

            # Si la respuesta no fue enviada aún, informar al usuario
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    embed=error_embed(
                        "Error inesperado",
                        "Ocurrió un error al ejecutar el comando. El desarrollador fue notificado.",
                    ),
                    ephemeral=True,
                )


# ---------------------------------------------------------------------------
# Punto de Entrada
# ---------------------------------------------------------------------------

async def main() -> None:
    """Función principal: valida config e inicia el bot."""
    # Detiene el programa si faltan variables de entorno críticas
    validate_config()

    bot = KutralBot()

    print("\n  Cargando módulos...")
    async with bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
"""
cogs/owner.py — Asistente Personal Privado
===============================================
Módulo EXCLUSIVO para el dueño del bot (OWNER_ID en .env).

SEGURIDAD:
    - Cada comando usa el decorador @is_owner() de utils/checks.py.
    - Todas las respuestas son efímeras (ephemeral=True).
    - Si alguien más intenta ejecutar estos comandos, Discord muestra
      un error de permisos sin revelar qué hace el comando.

Funcionalidades:
    Notas rápidas  -> /note add | list | delete
    Tareas         -> /task add | done | list
    Recordatorios  -> /remind <tiempo> <mensaje>
    Admin del bot  -> /reload <cog>

Persistencia:
    Las notas y tareas se guardan en SQLite (data/kutral.db).
    Los recordatorios usan asyncio.sleep() actualmente.
"""

import asyncio
import discord
from discord import app_commands
from discord.ext import commands

from data import database
from utils.checks import is_owner
from utils.embeds import success_embed, error_embed, info_embed


# ---------------------------------------------------------------------------
# Grupos de Subcomandos
# ---------------------------------------------------------------------------

class NoteGroup(app_commands.Group):
    """
    Grupo de comandos para gestión de notas personales.
    """

    def __init__(self) -> None:
        super().__init__(name="note", description="Gestiona tus notas personales")

    @app_commands.command(name="add", description="Guarda una nueva nota")
    @app_commands.describe(text="Contenido de la nota")
    @is_owner()
    async def add(self, interaction: discord.Interaction, text: str) -> None:
        """Persiste una nueva nota en la base de datos."""
        note_id = await database.add_note(interaction.user.id, text)
        await interaction.response.send_message(
            embed=success_embed("Nota guardada", f"Nota #{note_id} registrada:\n`{text}`"),
            ephemeral=True,
        )

    @app_commands.command(name="list", description="Muestra todas tus notas")
    @is_owner()
    async def list(self, interaction: discord.Interaction) -> None:
        """Recupera y muestra todas las notas del dueño."""
        notes = await database.get_notes(interaction.user.id)
        
        if not notes:
            await interaction.response.send_message(
                embed=info_embed("Tus Notas", "Sin notas guardadas."),
                ephemeral=True,
            )
            return

        description = ""
        for note in notes:
            # Formato de fecha simplificado
            date_str = note['created_at'].split('T')[0]
            description += f"**#{note['id']}** ({date_str}): {note['content']}\n"

        await interaction.response.send_message(
            embed=info_embed("Tus Notas", description),
            ephemeral=True,
        )

    @app_commands.command(name="delete", description="Elimina una nota por su ID")
    @app_commands.describe(note_id="ID numerico de la nota a eliminar (ver /note list)")
    @is_owner()
    async def delete(self, interaction: discord.Interaction, note_id: int) -> None:
        """Elimina una nota especifica de la base de datos."""
        deleted = await database.delete_note(interaction.user.id, note_id)
        if deleted:
            await interaction.response.send_message(
                embed=success_embed("Nota eliminada", f"Nota #{note_id} eliminada exitosamente."),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=error_embed("Error", f"No se encontro la nota #{note_id} o no te pertenece."),
                ephemeral=True,
            )


class TaskGroup(app_commands.Group):
    """
    Grupo de comandos para gestión de tareas pendientes.
    """

    def __init__(self) -> None:
        super().__init__(name="task", description="Gestiona tus tareas pendientes")

    @app_commands.command(name="add", description="Agrega una nueva tarea")
    @app_commands.describe(text="Descripcion de la tarea")
    @is_owner()
    async def add(self, interaction: discord.Interaction, text: str) -> None:
        """Crea una nueva tarea con estado pendiente."""
        task_id = await database.add_task(interaction.user.id, text)
        await interaction.response.send_message(
            embed=success_embed("Tarea agregada", f"Tarea #{task_id} registrada:\n`{text}`"),
            ephemeral=True,
        )

    @app_commands.command(name="done", description="Marca una tarea como completada")
    @app_commands.describe(task_id="ID numerico de la tarea a completar (ver /task list)")
    @is_owner()
    async def done(self, interaction: discord.Interaction, task_id: int) -> None:
        """Actualiza el estado de una tarea a completada."""
        completed = await database.complete_task(interaction.user.id, task_id)
        if completed:
            await interaction.response.send_message(
                embed=success_embed("Tarea completada", f"Tarea #{task_id} marcada como completada."),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=error_embed("Error", f"No se encontro la tarea pendiente #{task_id}."),
                ephemeral=True,
            )

    @app_commands.command(name="list", description="Muestra todas tus tareas activas")
    @is_owner()
    async def list(self, interaction: discord.Interaction) -> None:
        """Lista todas las tareas con estado pendiente."""
        tasks = await database.get_tasks(interaction.user.id, status="pending")
        
        if not tasks:
            await interaction.response.send_message(
                embed=info_embed("Tus Tareas", "Sin tareas pendientes."),
                ephemeral=True,
            )
            return

        description = ""
        for task in tasks:
            date_str = task['created_at'].split('T')[0]
            description += f"**#{task['id']}** ({date_str}): {task['content']}\n"

        await interaction.response.send_message(
            embed=info_embed("Tus Tareas", description),
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# Cog Principal
# ---------------------------------------------------------------------------

class Owner(commands.Cog, name="Asistente Personal"):
    """
    Cog del asistente personal privado del dueño del bot.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.bot.tree.add_command(NoteGroup())
        self.bot.tree.add_command(TaskGroup())

    async def cog_unload(self) -> None:
        """Limpia los grupos de comandos cuando el cog es descargado."""
        self.bot.tree.remove_command("note")
        self.bot.tree.remove_command("task")

    # -----------------------------------------------------------------------
    # Slash Commands directos (sin grupo)
    # -----------------------------------------------------------------------

    @app_commands.command(name="remind", description="Crea un recordatorio personal")
    @app_commands.describe(
        minutes="En cuantos minutos te recordare el mensaje",
        message="El mensaje del recordatorio",
    )
    @is_owner()
    async def remind(
        self,
        interaction: discord.Interaction,
        minutes: int,
        message: str,
    ) -> None:
        """Configura un recordatorio asíncrono."""
        await interaction.response.send_message(
            embed=success_embed(
                "Recordatorio creado",
                f"Te recordare en **{minutes} min**:\n`{message}`",
            ),
            ephemeral=True,
        )
        
        # Tarea de fondo
        async def send_reminder():
            await asyncio.sleep(minutes * 60)
            try:
                user = await self.bot.fetch_user(interaction.user.id)
                await user.send(embed=info_embed("Recordatorio", f"`{message}`"))
            except Exception as e:
                print(f"[Owner] Error enviando recordatorio: {e}")
                
        self.bot.loop.create_task(send_reminder())

    @app_commands.command(name="reload", description="Recarga un modulo del bot sin reiniciarlo")
    @app_commands.describe(cog="Nombre del cog a recargar (ej: music, moderation, ai_chat)")
    @is_owner()
    async def reload(self, interaction: discord.Interaction, cog: str) -> None:
        """Recarga un cog en caliente."""
        try:
            await self.bot.reload_extension(f"cogs.{cog}")
            await interaction.response.send_message(
                embed=success_embed(
                    "Cog recargado",
                    f"Modulo `cogs.{cog}` recargado correctamente.",
                ),
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(
                embed=error_embed("Error recargando", str(e)),
                ephemeral=True,
            )

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot) -> None:
    """Registra el cog Owner en el bot."""
    await bot.add_cog(Owner(bot))

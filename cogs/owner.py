"""
cogs/owner.py — Asistente Personal Privado 🔒
===============================================
Módulo EXCLUSIVO para el dueño del bot (OWNER_ID en .env).

SEGURIDAD:
    - Cada comando usa el decorador @is_owner() de utils/checks.py.
    - Todas las respuestas son efímeras (ephemeral=True): solo el dueño
      puede verlas, nadie más en el servidor.
    - Si alguien más intenta ejecutar estos comandos, Discord muestra
      un error de permisos sin revelar qué hace el comando.

Funcionalidades:
    📝 Notas rápidas  → /note add | list | delete
    ✅ Tareas         → /task add | done | list
    ⏰ Recordatorios  → /remind <tiempo> <mensaje>
    🔧 Admin del bot  → /reload <cog>

Persistencia:
    Las notas y tareas se guardan en SQLite (data/kutral.db).
    Los recordatorios usan asyncio.sleep() o discord.ext.tasks.

Grupos de comandos:
    Se usan app_commands.Group para agrupar comandos relacionados,
    lo que genera subcomandos en Discord: /note add, /note list, etc.
"""

import discord
from discord import app_commands
from discord.ext import commands

from utils.checks import is_owner
from utils.embeds import success_embed, error_embed, info_embed, primary_embed


# ---------------------------------------------------------------------------
# Grupos de Subcomandos
# ---------------------------------------------------------------------------

class NoteGroup(app_commands.Group):
    """
    Grupo de comandos para gestión de notas personales.

    Subcomandos:
        /note add <text>     — Guarda una nueva nota
        /note list           — Lista todas las notas
        /note delete <id>    — Elimina una nota por su ID
    """

    def __init__(self) -> None:
        super().__init__(name="note", description="Gestiona tus notas personales")

    @app_commands.command(name="add", description="Guarda una nueva nota")
    @app_commands.describe(text="Contenido de la nota")
    @is_owner()
    async def add(self, interaction: discord.Interaction, text: str) -> None:
        """
        Persiste una nueva nota en la base de datos con timestamp automático.

        Args:
            text: Contenido de la nota a guardar.
        """
        # TODO: Insertar nota en SQLite: (id, owner_id, text, created_at)
        await interaction.response.send_message(
            embed=success_embed("Nota guardada", f"📝 `{text}`\n*(Función en construcción)*"),
            ephemeral=True,
        )

    @app_commands.command(name="list", description="Muestra todas tus notas")
    @is_owner()
    async def list(self, interaction: discord.Interaction) -> None:
        """
        Recupera y muestra todas las notas del dueño desde la base de datos.
        Las notas se muestran numeradas con su ID y fecha de creación.
        """
        # TODO: Consultar SQLite y construir embed con la lista de notas
        await interaction.response.send_message(
            embed=info_embed("Tus Notas", "📋 Sin notas guardadas.\n*(Función en construcción)*"),
            ephemeral=True,
        )

    @app_commands.command(name="delete", description="Elimina una nota por su ID")
    @app_commands.describe(note_id="ID numérico de la nota a eliminar (ver /note list)")
    @is_owner()
    async def delete(self, interaction: discord.Interaction, note_id: int) -> None:
        """
        Elimina una nota específica de la base de datos.

        Args:
            note_id: ID de la nota (obtenido de /note list).
        """
        # TODO: Eliminar nota de SQLite por ID y confirmar al dueño
        await interaction.response.send_message(
            embed=success_embed("Nota eliminada", f"🗑️ Nota `#{note_id}` eliminada.\n*(Función en construcción)*"),
            ephemeral=True,
        )


class TaskGroup(app_commands.Group):
    """
    Grupo de comandos para gestión de tareas pendientes.

    Subcomandos:
        /task add <text>  — Agrega una nueva tarea
        /task done <id>   — Marca una tarea como completada
        /task list        — Lista todas las tareas activas
    """

    def __init__(self) -> None:
        super().__init__(name="task", description="Gestiona tus tareas pendientes")

    @app_commands.command(name="add", description="Agrega una nueva tarea")
    @app_commands.describe(text="Descripción de la tarea")
    @is_owner()
    async def add(self, interaction: discord.Interaction, text: str) -> None:
        """
        Crea una nueva tarea con estado 'pendiente' en la base de datos.

        Args:
            text: Descripción de la tarea.
        """
        # TODO: Insertar tarea en SQLite: (id, owner_id, text, status, created_at)
        await interaction.response.send_message(
            embed=success_embed("Tarea agregada", f"✅ `{text}`\n*(Función en construcción)*"),
            ephemeral=True,
        )

    @app_commands.command(name="done", description="Marca una tarea como completada")
    @app_commands.describe(task_id="ID numérico de la tarea a completar (ver /task list)")
    @is_owner()
    async def done(self, interaction: discord.Interaction, task_id: int) -> None:
        """
        Actualiza el estado de una tarea de 'pendiente' a 'completada'.

        Args:
            task_id: ID de la tarea (obtenido de /task list).
        """
        # TODO: UPDATE en SQLite: status='done', completed_at=now() WHERE id=task_id
        await interaction.response.send_message(
            embed=success_embed("Tarea completada", f"🎉 Tarea `#{task_id}` marcada como completada.\n*(Función en construcción)*"),
            ephemeral=True,
        )

    @app_commands.command(name="list", description="Muestra todas tus tareas activas")
    @is_owner()
    async def list(self, interaction: discord.Interaction) -> None:
        """Lista todas las tareas con estado 'pendiente' desde la base de datos."""
        # TODO: Consultar SQLite y construir embed con tareas pendientes
        await interaction.response.send_message(
            embed=info_embed("Tus Tareas", "📋 Sin tareas pendientes.\n*(Función en construcción)*"),
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# Cog Principal
# ---------------------------------------------------------------------------

class Owner(commands.Cog, name="Asistente Personal"):
    """
    Cog del asistente personal privado del dueño del bot.

    Attributes:
        bot: Instancia principal del bot.

    Note:
        Los grupos NoteGroup y TaskGroup se registran en el árbol de comandos
        directamente desde __init__ para que aparezcan como /note y /task.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Registrar los grupos de subcomandos en el árbol de la aplicación
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
        minutes="En cuántos minutos te recordaré el mensaje",
        message="El mensaje del recordatorio",
    )
    @is_owner()
    async def remind(
        self,
        interaction: discord.Interaction,
        minutes: int,
        message: str,
    ) -> None:
        """
        Configura un recordatorio que enviará un DM al dueño después del tiempo indicado.

        Implementación recomendada:
            Usar asyncio.create_task(asyncio.sleep(minutes * 60)) + DM al dueño.
            Para recordatorios persistentes (sobreviven reinicios), guardar en SQLite
            y usar discord.ext.tasks para revisarlos periódicamente.

        Args:
            minutes: Tiempo de espera en minutos.
            message: Contenido del recordatorio.
        """
        # TODO: Crear tarea asíncrona con asyncio.sleep y enviar DM al dueño
        await interaction.response.send_message(
            embed=success_embed(
                "Recordatorio creado",
                f"⏰ Te recordaré en **{minutes} min**:\n`{message}`\n*(Función en construcción)*",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="reload", description="Recarga un módulo del bot sin reiniciarlo")
    @app_commands.describe(cog="Nombre del cog a recargar (ej: music, moderation, ai_chat)")
    @is_owner()
    async def reload(self, interaction: discord.Interaction, cog: str) -> None:
        """
        Recarga un cog en caliente sin necesidad de reiniciar el bot.

        Útil durante el desarrollo para aplicar cambios de código al instante.
        El nombre del cog debe coincidir con el nombre del archivo en /cogs/.

        Args:
            cog: Nombre del módulo sin extensión (ej: "music" → cogs.music).
        """
        # TODO: Llamar await self.bot.reload_extension(f"cogs.{cog}") y manejar errores
        await interaction.response.send_message(
            embed=success_embed(
                "Cog recargado",
                f"🔄 Módulo `cogs.{cog}` recargado correctamente.\n*(Función en construcción)*",
            ),
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# Setup — Requerido por discord.py para cargar el cog
# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot) -> None:
    """Registra el cog Owner en el bot."""
    await bot.add_cog(Owner(bot))

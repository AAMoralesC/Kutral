"""
cogs/moderation.py — Módulo de Moderación 🛡️
===============================================
Comandos de administración y disciplina para el servidor.

Todos los comandos requieren el permiso 'Manage Messages' o 'Administrator'.
Las acciones quedan registradas en la base de datos para auditoría futura.

Comandos disponibles:
    /ban      <user> [reason]    — Banea a un usuario del servidor
    /kick     <user> [reason]    — Expulsa a un usuario del servidor
    /mute     <user> [duration]  — Silencia a un usuario temporalmente (timeout nativo)
    /unmute   <user>             — Quita el silencio a un usuario
    /warn     <user> <reason>    — Registra una advertencia formal en la DB
    /warnings <user>             — Consulta el historial de advertencias
    /clearwarns <user>           — Borra todas las advertencias de un usuario
    /clear    <amount>           — Elimina mensajes del canal actual

Seguridad:
    Antes de ejecutar ban/kick/mute, se verifica la jerarquía de roles:
      - El usuario objetivo debe tener menos permisos que el moderador.
      - El usuario objetivo no puede ser el propio bot.
      - Un moderador no puede actuar sobre otro moderador de igual rango.
"""

from datetime import timedelta, datetime

import discord
from discord import app_commands
from discord.ext import commands

import config
from data import database as db
from utils.checks import is_moderator, guild_only
from utils.embeds import success_embed, error_embed, warning_embed, info_embed


class Moderation(commands.Cog, name="Moderación"):
    """
    Cog de moderación del servidor.

    Attributes:
        bot: Instancia principal del bot.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # -----------------------------------------------------------------------
    # Helpers internos
    # -----------------------------------------------------------------------

    def _check_hierarchy(
        self,
        interaction: discord.Interaction,
        target: discord.Member,
    ) -> str | None:
        """
        Verifica que la acción de moderación sea válida según la jerarquía de roles.

        Reglas:
            1. No se puede actuar sobre el propio bot.
            2. No se puede actuar sobre el dueño del servidor.
            3. El objetivo debe tener un rol inferior al del moderador.
            4. El objetivo debe tener un rol inferior al del bot.

        Args:
            interaction: Contexto de la interacción (contiene al moderador).
            target:      Miembro de Discord sobre quien se ejecuta la acción.

        Returns:
            None si la jerarquía es válida.
            str  con el mensaje de error si la acción no está permitida.
        """
        # No se puede actuar sobre el bot mismo
        if target.id == self.bot.user.id:
            return "No puedo aplicar acciones de moderación sobre mí mismo."

        # No se puede actuar sobre el dueño del servidor
        if target.id == interaction.guild.owner_id:
            return "No puedes moderar al dueño del servidor."

        # El objetivo no puede tener un rol igual o superior al moderador
        moderator = interaction.user
        if target.top_role >= moderator.top_role:
            return (
                f"No puedes moderar a **{target.display_name}** porque su rol "
                f"(**{target.top_role.name}**) es igual o superior al tuyo."
            )

        # El objetivo no puede tener un rol igual o superior al del bot
        bot_member = interaction.guild.me
        if target.top_role >= bot_member.top_role:
            return (
                f"No puedo moderar a **{target.display_name}** porque su rol "
                f"(**{target.top_role.name}**) es igual o superior al mío. "
                f"Mueve mi rol más arriba en la configuración del servidor."
            )

        return None  # Sin problemas, se puede proceder

    async def _notify_user(
        self,
        user: discord.Member,
        action: str,
        guild_name: str,
        reason: str,
        extra: str = "",
    ) -> bool:
        """
        Intenta enviar un DM al usuario notificándole la acción de moderación.

        Se usa DM para que la notificación sea privada y discreta.
        Si el usuario tiene DMs desactivados, falla silenciosamente.

        Args:
            user:       Miembro a notificar.
            action:     Texto de la acción (ej: "baneado", "silenciado").
            guild_name: Nombre del servidor donde ocurrió la acción.
            reason:     Motivo de la acción.
            extra:      Información adicional opcional (ej: duración del mute).

        Returns:
            True si el DM fue enviado, False si el usuario tiene DMs desactivados.
        """
        embed = discord.Embed(
            title=f"⚠️  Has sido {action} en {guild_name}",
            description=f"**Razón:** {reason}\n{extra}",
            color=config.COLOR_WARNING,
            timestamp=datetime.utcnow(),
        )
        embed.set_footer(text="Si crees que esto es un error, contacta a un administrador.")

        try:
            await user.send(embed=embed)
            return True
        except (discord.Forbidden, discord.HTTPException):
            # El usuario tiene DMs bloqueados o un error de red — no es crítico
            return False

    # -----------------------------------------------------------------------
    # Slash Commands
    # -----------------------------------------------------------------------

    @app_commands.command(name="ban", description="Banea a un usuario del servidor")
    @app_commands.describe(
        user="El usuario que será baneado",
        reason="Razón del baneo (aparece en el registro de auditoría de Discord)",
        delete_days="Días de mensajes a eliminar del usuario baneado (0-7)",
    )
    @is_moderator()
    @guild_only()
    async def ban(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "Sin razón especificada",
        delete_days: app_commands.Range[int, 0, 7] = 0,
    ) -> None:
        """
        Banea permanentemente a un miembro del servidor.

        Flujo:
            1. Verificar jerarquía de roles.
            2. Intentar notificar al usuario por DM (antes del ban, después no puede recibir DMs).
            3. Ejecutar guild.ban().
            4. Confirmar al moderador con embed.

        Args:
            user:        Miembro de Discord a banear.
            reason:      Motivo del baneo (queda en el log de auditoría de Discord).
            delete_days: Cantidad de días de mensajes del usuario a borrar (0–7).
        """
        # 1. Verificar jerarquía
        error_msg = self._check_hierarchy(interaction, user)
        if error_msg:
            await interaction.response.send_message(
                embed=error_embed("No se puede banear", error_msg),
                ephemeral=True,
            )
            return

        # 2. Notificar al usuario por DM ANTES del ban (después ya no estará en el servidor)
        dm_sent = await self._notify_user(
            user, "baneado", interaction.guild.name, reason
        )

        # 3. Ejecutar el ban
        try:
            await interaction.guild.ban(
                user,
                reason=f"[{interaction.user}] {reason}",
                delete_message_days=delete_days,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("Sin permisos", "No tengo permisos para banear usuarios."),
                ephemeral=True,
            )
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=error_embed("Error de Discord", f"No se pudo completar el ban: {e}"),
                ephemeral=True,
            )
            return

        # 4. Confirmar al moderador
        dm_note = "" if dm_sent else "\n> ⚠️ No se pudo notificar al usuario por DM."
        await interaction.response.send_message(
            embed=success_embed(
                "Usuario baneado",
                f"🔨 **{user.display_name}** (`{user.id}`) ha sido baneado.\n"
                f"**Razón:** {reason}{dm_note}",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="kick", description="Expulsa a un usuario del servidor")
    @app_commands.describe(
        user="El usuario que será expulsado",
        reason="Razón de la expulsión",
    )
    @is_moderator()
    @guild_only()
    async def kick(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "Sin razón especificada",
    ) -> None:
        """
        Expulsa (kick) a un miembro del servidor.

        A diferencia del ban, el usuario puede volver al servidor con
        una nueva invitación. Se le notifica por DM antes de la expulsión.

        Args:
            user:   Miembro de Discord a expulsar.
            reason: Motivo de la expulsión.
        """
        # 1. Verificar jerarquía
        error_msg = self._check_hierarchy(interaction, user)
        if error_msg:
            await interaction.response.send_message(
                embed=error_embed("No se puede expulsar", error_msg),
                ephemeral=True,
            )
            return

        # 2. Notificar por DM antes del kick
        dm_sent = await self._notify_user(
            user, "expulsado", interaction.guild.name, reason
        )

        # 3. Ejecutar el kick
        try:
            await interaction.guild.kick(
                user,
                reason=f"[{interaction.user}] {reason}",
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("Sin permisos", "No tengo permisos para expulsar usuarios."),
                ephemeral=True,
            )
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=error_embed("Error de Discord", f"No se pudo completar el kick: {e}"),
                ephemeral=True,
            )
            return

        # 4. Confirmar al moderador
        dm_note = "" if dm_sent else "\n> ⚠️ No se pudo notificar al usuario por DM."
        await interaction.response.send_message(
            embed=success_embed(
                "Usuario expulsado",
                f"👢 **{user.display_name}** (`{user.id}`) fue expulsado.\n"
                f"**Razón:** {reason}{dm_note}",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="mute", description="Silencia a un usuario temporalmente")
    @app_commands.describe(
        user="El usuario que será silenciado",
        duration="Duración en minutos (mín: 1, máx: 40320 = 28 días)",
        reason="Razón del silencio",
    )
    @is_moderator()
    @guild_only()
    async def mute(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        duration: app_commands.Range[int, 1, 40320] = 10,
        reason: str = "Sin razón especificada",
    ) -> None:
        """
        Aplica un timeout (silencio) usando la función nativa de Discord.

        Ventaja sobre el sistema de rol "Muted":
            - No requiere crear ni gestionar un rol especial.
            - El timeout es manejado directamente por Discord.
            - Límite máximo de Discord: 28 días (40320 minutos).

        Args:
            user:     Miembro a silenciar.
            duration: Duración en minutos (1 – 40320).
            reason:   Motivo del silencio.
        """
        # 1. Verificar jerarquía
        error_msg = self._check_hierarchy(interaction, user)
        if error_msg:
            await interaction.response.send_message(
                embed=error_embed("No se puede silenciar", error_msg),
                ephemeral=True,
            )
            return

        # Calcular tiempo de expiración legible para el DM y el embed
        until = discord.utils.utcnow() + timedelta(minutes=duration)

        # Formatear duración de forma legible (ej: "2h 30m" en vez de "150 minutos")
        hours, mins = divmod(duration, 60)
        days, hours = divmod(hours, 24)
        parts = []
        if days:  parts.append(f"{days}d")
        if hours: parts.append(f"{hours}h")
        if mins:  parts.append(f"{mins}m")
        duration_str = " ".join(parts) if parts else f"{duration}m"

        # 2. Notificar al usuario por DM
        await self._notify_user(
            user, "silenciado", interaction.guild.name, reason,
            extra=f"**Duración:** {duration_str}",
        )

        # 3. Aplicar el timeout nativo de Discord
        try:
            await user.timeout(until, reason=f"[{interaction.user}] {reason}")
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("Sin permisos", "No tengo permisos para silenciar usuarios."),
                ephemeral=True,
            )
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=error_embed("Error de Discord", f"No se pudo aplicar el silencio: {e}"),
                ephemeral=True,
            )
            return

        # 4. Confirmar
        await interaction.response.send_message(
            embed=success_embed(
                "Usuario silenciado",
                f"🔇 **{user.display_name}** fue silenciado por **{duration_str}**.\n"
                f"**Razón:** {reason}",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="unmute", description="Quita el silencio a un usuario")
    @app_commands.describe(user="El usuario al que se le quitará el silencio")
    @is_moderator()
    @guild_only()
    async def unmute(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
    ) -> None:
        """
        Elimina el timeout activo de un miembro antes de que expire.

        Pasar None a member.timeout() cancela cualquier timeout activo.
        Si el usuario no tiene timeout, se informa sin hacer nada.
        """
        # Verificar que el usuario realmente está silenciado
        if not user.is_timed_out():
            await interaction.response.send_message(
                embed=warning_embed(
                    "Sin silencio activo",
                    f"**{user.display_name}** no tiene ningún silencio activo.",
                ),
                ephemeral=True,
            )
            return

        try:
            # Pasar None cancela el timeout activo
            await user.timeout(None, reason=f"[{interaction.user}] Silencio removido manualmente")
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("Sin permisos", "No tengo permisos para remover el silencio."),
                ephemeral=True,
            )
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=error_embed("Error de Discord", f"No se pudo remover el silencio: {e}"),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=success_embed(
                "Silencio removido",
                f"🔊 **{user.display_name}** puede volver a hablar.",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="warn", description="Registra una advertencia formal para un usuario")
    @app_commands.describe(
        user="El usuario que recibirá la advertencia",
        reason="Motivo de la advertencia",
    )
    @is_moderator()
    @guild_only()
    async def warn(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str,
    ) -> None:
        """
        Registra una advertencia formal en la base de datos y notifica al usuario.

        El historial de advertencias puede consultarse con /warnings.
        Las advertencias persisten aunque el usuario abandone y regrese al servidor.

        Args:
            user:   Miembro que recibirá la advertencia.
            reason: Motivo de la advertencia (obligatorio).
        """
        # No tiene sentido advertir a bots
        if user.bot:
            await interaction.response.send_message(
                embed=error_embed("Acción inválida", "No puedes advertir a un bot."),
                ephemeral=True,
            )
            return

        # Guardar en la base de datos
        warning_id = await db.add_warning(
            guild_id=interaction.guild_id,
            user_id=user.id,
            moderator_id=interaction.user.id,
            reason=reason,
        )

        # Consultar total de advertencias del usuario para mostrar en el embed
        all_warnings = await db.get_warnings(interaction.guild_id, user.id)
        total = len(all_warnings)

        # Notificar al usuario por DM
        await self._notify_user(
            user, "advertido", interaction.guild.name, reason,
            extra=f"Esta es tu advertencia número **{total}**.",
        )

        await interaction.response.send_message(
            embed=warning_embed(
                "Advertencia registrada",
                f"⚠️ **{user.display_name}** recibió la advertencia **#{warning_id}**.\n"
                f"**Razón:** {reason}\n"
                f"**Total de advertencias:** {total}",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="warnings", description="Muestra el historial de advertencias de un usuario")
    @app_commands.describe(user="El usuario a consultar")
    @is_moderator()
    @guild_only()
    async def warnings_cmd(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
    ) -> None:
        """
        Recupera y muestra todas las advertencias de un usuario en este servidor.

        Cada advertencia muestra: ID, razón, moderador que la aplicó y fecha.
        """
        warns = await db.get_warnings(interaction.guild_id, user.id)

        if not warns:
            await interaction.response.send_message(
                embed=info_embed(
                    f"Sin advertencias — {user.display_name}",
                    "✅ Este usuario no tiene advertencias registradas.",
                ),
                ephemeral=True,
            )
            return

        # Construir embed con la lista de advertencias
        embed = discord.Embed(
            title=f"⚠️  Advertencias de {user.display_name}",
            description=f"Total: **{len(warns)}** advertencia(s)",
            color=config.COLOR_WARNING,
        )
        embed.set_thumbnail(url=user.display_avatar.url)

        for warn in warns:
            # Intentar resolver el ID del moderador a su nombre
            moderator = interaction.guild.get_member(warn["moderator_id"])
            mod_name  = moderator.display_name if moderator else f"ID {warn['moderator_id']}"

            # Formatear la fecha ISO 8601 a algo más legible
            try:
                dt = datetime.fromisoformat(warn["created_at"])
                date_str = dt.strftime("%d/%m/%Y %H:%M UTC")
            except (ValueError, TypeError):
                date_str = warn["created_at"]

            embed.add_field(
                name=f"Advertencia #{warn['id']}  —  {date_str}",
                value=f"**Razón:** {warn['reason']}\n**Por:** {mod_name}",
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="clearwarns", description="Borra todas las advertencias de un usuario")
    @app_commands.describe(user="El usuario al que se le borrarán todas las advertencias")
    @is_moderator()
    @guild_only()
    async def clearwarns(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
    ) -> None:
        """
        Elimina todo el historial de advertencias de un usuario en este servidor.

        Útil cuando un usuario ha mejorado su comportamiento y se quiere
        darle un "borrón y cuenta nueva".
        """
        deleted = await db.clear_warnings(interaction.guild_id, user.id)

        if deleted == 0:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Sin advertencias",
                    f"**{user.display_name}** no tenía advertencias que borrar.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=success_embed(
                "Advertencias eliminadas",
                f"🗑️ Se borraron **{deleted}** advertencia(s) de **{user.display_name}**.",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="clear", description="Elimina mensajes del canal actual")
    @app_commands.describe(
        amount=f"Cantidad de mensajes a borrar (1–{config.MODERATION_MAX_CLEAR})",
    )
    @is_moderator()
    @guild_only()
    async def clear(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, config.MODERATION_MAX_CLEAR],
    ) -> None:
        """
        Purga mensajes del canal donde se ejecuta el comando.

        Notas técnicas:
            - Discord solo permite bulk_delete en mensajes de menos de 14 días.
            - channel.purge() maneja esto automáticamente: borra en lote los
              recientes y uno a uno los más antiguos (más lento, pero funciona).
            - El mensaje de confirmación es efímero para no dejar rastro visible.

        Args:
            amount: Número de mensajes a eliminar (1 – MODERATION_MAX_CLEAR).
        """
        # Diferir la respuesta: purge puede tardar varios segundos
        await interaction.response.defer(ephemeral=True)

        try:
            # purge() retorna la lista de mensajes eliminados
            deleted = await interaction.channel.purge(limit=amount)
        except discord.Forbidden:
            await interaction.followup.send(
                embed=error_embed("Sin permisos", "No tengo permisos para borrar mensajes aquí."),
                ephemeral=True,
            )
            return
        except discord.HTTPException as e:
            await interaction.followup.send(
                embed=error_embed("Error de Discord", f"No se pudo completar la purga: {e}"),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            embed=success_embed(
                "Mensajes eliminados",
                f"🗑️ Se eliminaron **{len(deleted)}** mensaje(s) de este canal.",
            ),
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# Setup — Requerido por discord.py para cargar el cog
# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot) -> None:
    """Registra el cog Moderation en el bot."""
    await bot.add_cog(Moderation(bot))

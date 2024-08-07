import logging
import traceback
import types
from functools import partial

import disnake
from disnake.ext import commands
from disnake.ext.commands.context import AnyContext

from mediamagic.bot import MediaMagic
from mediamagic.constants import Client
from mediamagic.exceptions import NotPremium, Premium_Owner
from mediamagic.utils.messages import DeleteButton

logger = logging.getLogger(__name__)


class ErrorHandler(commands.Cog):
    def __init__(self, bot: MediaMagic) -> None:
        self.bot = bot

    @staticmethod
    def error_embed(title: str, description: str) -> disnake.Embed:
        return disnake.Embed(
            color=disnake.Colour.red(), title=title, description=description
        )

    async def handle_user_input_error(
        self, error: commands.UserInputError
    ) -> disnake.Embed:
        """Handler for User Input Error"""
        return self.error_embed(error.__class__.__name__, str(error))

    async def handler_bot_missing_perms(
        self, ctx: AnyContext, error: commands.BotMissingPermissions | disnake.Forbidden
    ) -> None:
        """Handler for Bot Missing Permissions error"""
        embed = self.error_embed("Permission Failure", str(error))
        bot_perms = disnake.Permissions()
        if not isinstance(
            ctx.channel, (disnake.channel.DMChannel, disnake.channel.PartialMessageable)
        ):

            bot_perms = ctx.channel.permissions_for(ctx.me)  # type: ignore[reportArgumentType]
        logger.info(type(ctx.channel))
        if bot_perms >= disnake.Permissions(send_messages=True, embed_links=True):
            await ctx.send_error(embed=embed)  # type: ignore[reportAttributeAccessIssue]
        elif bot_perms >= disnake.Permissions(send_messages=True):
            await ctx.send_error(  # type: ignore[reportAttributeAccessIssue]
                "**Permissions Failure**\n\nI am missing required permission to perform this command."
            )
            logger.warning(
                f"Missing partial required permission for {ctx.channel}. I am able to send messages but not embeds."
            )
        else:
            logger.error(f"Unable to send error messages to {ctx.channel}")

    async def handle_check_failure(
        self, ctx: AnyContext, error: commands.CheckFailure
    ) -> disnake.Embed | None:
        """Handler for Check Failure Error"""
        title = "Check Failure"
        embed = None
        if isinstance(error, Premium_Owner):
            embed = self.error_embed(
                "Premium Owner",
                "You don't have `manage_guild` permission to run this command. Try adding me on your server",
            )
        elif isinstance(error, NotPremium):
            embed = self.error_embed(
                "You are not a premium user",
                "Join the "
                f"[support server](https://discord.gg/{Client.support_server_invite}) "
                "to buy or know more about premium.",
            )
        elif isinstance(error, commands.CheckAnyFailure):
            title = str(error.checks[-1])
        elif isinstance(error, commands.PrivateMessageOnly):
            title = "Dms Only"
        elif isinstance(error, commands.NoPrivateMessage):
            title = "Server Only"
        elif isinstance(error, commands.NotOwner):
            return None
        elif isinstance(error, commands.BotMissingPermissions):
            await self.handler_bot_missing_perms(ctx, error)
            return None
        else:
            title = "Error"
        if embed is None:
            embed = self.error_embed(title, str(error))
        return embed

    def make_error_message(
        self,
        ctx: AnyContext,
        *,
        extended_context: bool = True,
    ) -> str:
        """Logs error with enough relevant context properly to fix the issue"""
        if isinstance(ctx, commands.Context):
            msg = (
                f"Error Occured in prefix command {ctx.command and ctx.command.qualified_name} in guild"
                f" {ctx.guild and ctx.guild.id} with user {ctx.author.id}"
            )
        elif isinstance(ctx, disnake.ApplicationCommandInteraction):
            cmd_type = ctx.data.type
            try:
                cmd_type = cmd_type.name
            except AttributeError:
                pass
            msg = (
                f"Error occured in app command {ctx.application_command.qualified_name} of type {cmd_type} in guild"
                f" {ctx.guild_id} with user {ctx.author.id}\n"
            )
        elif isinstance(ctx, disnake.MessageInteraction):
            msg = (
                f"Error occured in message component '{ctx.component.custom_id}' in gulid"
                f" {ctx.guild_id} with user {ctx.author.id}\n"
            )
        else:
            msg = "Error occured in unkown event\n"

        if not extended_context:
            return msg

        msg_type = getattr(type(ctx), "__name__", None) or str(type(ctx))
        msg += f"{msg_type}:\n"
        skip_attrs = {"token", "bot", "client", "send_error"}
        for attr in dir(ctx):
            if attr in skip_attrs or attr.startswith("_"):
                continue
            prop = getattr(ctx, attr, "???")
            if isinstance(prop, (types.FunctionType, partial, types.MethodType)):
                continue
            msg += f"\t{attr}={prop}\n"
        return msg

    async def command_error(self, ctx: AnyContext, error: commands.CommandError):
        if getattr(error, "handled", False):
            logger.debug(
                f"Command {ctx.command} had its error handler already. Skipping it!"  # type: ignore[reportAttributeAccessIssue]
            )
            return

        if isinstance(ctx, commands.CommandNotFound):
            return

        embed: disnake.Embed | None = None
        should_respond = True

        if isinstance(error, commands.UserInputError):
            embed = await self.handle_user_input_error(error)
        elif isinstance(error, commands.errors.CheckFailure):
            embed = await self.handle_check_failure(ctx, error)
            if embed is None:
                should_respond = False
        elif isinstance(error, commands.DisabledCommand):
            if not ctx.command.hidden:  # type: ignore[reportAttributeAccessIssue]
                msg = f"Command `{ctx.invoked_with}` is disabled."  # type: ignore[reportAttributeAccessIssue]
                if reason := ctx.command.extras.get("disabled_reason", None):  # type: ignore[reportAttributeAccessIssue]
                    msg += f"\nReason: {reason}"
                embed = self.error_embed("Command Disabled", msg)
        elif isinstance(error, (commands.CommandInvokeError, commands.ConversionError)):
            if isinstance(error.original, disnake.Forbidden):
                logger.warn(f"Permission error ouccured in {ctx.command}.")  # type: ignore[reportAttributeAccessIssue]
                await self.handler_bot_missing_perms(ctx, error.original)
                should_respond = False
            else:

                # Generic Error
                try:
                    msg = self.make_error_message(
                        ctx, extended_context=Client.debug_mode
                    )
                except Exception as e:
                    logger.error(
                        "Error occured in building up full context log for an error",
                        exc_info=e,
                    )
                    msg = "Error ouccured"
                logger.error(msg, exc_info=error.original)

                # Built in command msg
                title = "Internal Error"
                error_str = "".join(
                    traceback.format_exception(
                        type(error.original),
                        value=error.original,
                        tb=error.original.__traceback__,
                        limit=-3,
                    )
                ).replace("``", "`\u200b`")
                if len(error_str) > 3000:
                    error_str = error_str[-3000:]
                msg = (
                    "Something went wrong internally in the action you were trying to execute. "
                    "Please report this error to "
                    f"the [Support Server](https://discord.gg/{Client.support_server_invite})."
                    f"\n\n ```py\n{error_str}\n```"
                )
                embed = self.error_embed(title, msg)
        if not should_respond:
            logger.debug("Not responding to error")
            return
        if embed is None:
            embed = self.error_embed("", str(error))

        await ctx.send_error(embed=embed)  # type: ignore[reportAttributeAccessIssue]

    @commands.Cog.listener(name="on_command_error")
    @commands.Cog.listener(name="on_slash_command_error")
    @commands.Cog.listener(name="on_message_command_error")
    async def error_handler(
        self, ctx: AnyContext, error: commands.CommandError
    ) -> None:
        """Generic handler for every error"""
        components = disnake.ui.MessageActionRow()
        components.add_button(
            style=disnake.ButtonStyle.link,
            label="Support Server",
            url=f"https://discord.gg/{Client.support_server_invite}",
        )

        if isinstance(ctx, commands.Context):
            components.insert_item(0, DeleteButton(ctx.author.id))
            ctx.send_error = partial(ctx.send, components=components)  # type: ignore[reportAttributeAccessIssue]
        elif isinstance(ctx, disnake.Interaction):
            if ctx.response.is_done():
                components.insert_item(0, DeleteButton(ctx.author.id))
                ctx.send_error = partial(  # type: ignore[reportAttributeAccessIssue]
                    ctx.followup.send, ephemeral=True, components=components
                )
            else:
                ctx.send_error = partial(  # type: ignore[reportAttributeAccessIssue]
                    ctx.send, ephemeral=True, components=components
                )

            if isinstance(
                ctx,
                (
                    disnake.ApplicationCommandInteraction,
                    disnake.MessageCommandInteraction,
                    disnake.UserCommandInteraction,
                ),
            ):
                ctx.command = ctx.application_command  # type: ignore[reportAttributeAccessIssue]
            elif isinstance(
                ctx, (disnake.MessageInteraction, disnake.ModalInteraction)
            ):
                ctx.command = ctx.message  # todo: this is working because of lib bug

        try:
            await self.command_error(ctx, error)
        except Exception as e:
            logger.error("Error occured in error handler", exc_info=e)


def setup(client: MediaMagic) -> None:
    client.add_cog(ErrorHandler(client))

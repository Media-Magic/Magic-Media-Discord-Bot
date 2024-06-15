import logging

import disnake
from disnake.ext import commands

from mediamagic.bot import MediaMagic

logger = logging.getLogger(__name__)
CUSTOM_DELETE_ID = "DELETE"


class DeleteButtonListener(commands.Cog, slash_command_attrs={"dm_permission": False}):
    """Handles Delete Button"""

    def __init__(self, client: MediaMagic) -> None:
        self.bot = client

    # button schema
    # PREFIX:PERMS:USER_ID:MESSAGE_ID
    @commands.Cog.listener("on_button_click")
    async def handle_delete_button(
        self, interaction: disnake.MessageInteraction
    ) -> None:
        """Deletes a message if a user is authorized"""
        if not interaction.component.custom_id:
            return
        if not interaction.component.custom_id.startswith(CUSTOM_DELETE_ID):
            return

        logger.debug(
            f"{self.__class__.__name__} recv: {interaction.component.custom_id}"
        )

        custom_id = interaction.component.custom_id.removeprefix(CUSTOM_DELETE_ID)

        perms, user_id, *msg_id = custom_id.split(":")

        delete_msg = None
        if msg_id:
            if msg_id[0]:
                delete_msg = int(msg_id[0])

        perms, user_id = int(perms), int(user_id)

        if not (is_orignal_author := interaction.author.id == user_id):
            permissions = disnake.Permissions(perms)
            user_permissions = interaction.permissions
            if not permissions.value & user_permissions.value:
                await interaction.response.send_message(
                    "Sorry, this delete button is not for you!",
                    ephemeral=True,
                    delete_after=5,
                )
                return

        if isinstance(
            interaction.channel,
            (disnake.TextChannel, disnake.Thread, disnake.VoiceChannel),
        ) and isinstance(interaction.me, disnake.Member):
            if (
                not hasattr(interaction.channel, "guild")
                or not (
                    myperms := interaction.channel.permissions_for(interaction.me)
                ).read_messages
            ):

                await interaction.response.defer()
                await interaction.delete_original_message()
                return

            await interaction.message.delete()

            if not delete_msg or not myperms.manage_messages or not is_orignal_author:
                return

            if msg := interaction.bot.get_message(delete_msg):
                if msg.edited_at:
                    return
            else:
                msg = interaction.channel.get_partial_message(delete_msg)

            try:
                await msg.delete()
            except disnake.NotFound:
                ...
            except disnake.Forbidden:
                logger.warning("Cache is unreliable or something is weird")
        else:
            logger.debug(f"Interaction's channel don't have required type.")


def setup(client: MediaMagic):
    client.add_cog(DeleteButtonListener(client))

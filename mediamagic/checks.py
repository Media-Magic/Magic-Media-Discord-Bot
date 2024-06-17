import logging

import disnake
from disnake.ext import commands

from mediamagic.constants import Client
from mediamagic.exceptions import NotPremium, Premium_Owner

logger = logging.getLogger(__name__)


def is_guild_or_bot_owner():
    def predicate(inter: disnake.GuildCommandInteraction):
        return (
            inter.guild is not None
            and inter.guild.owner_id == inter.author.id
            or inter.author.id == inter.bot.owner_id
        )

    return commands.check(predicate)  # type: ignore[reportArgumentType]


def is_premium_owner():
    def predicate(inter: disnake.GuildCommandInteraction) -> bool:
        if Client.debug_mode:
            return True
        server = inter.bot.get_guild(Client.premium_server)
        uid = inter.author.id
        if not server or not Client.premium_role:
            raise Premium_Owner
        elif member := server.get_member(uid):
            if (
                member.get_role(Client.premium_role)
                and inter.author.guild_permissions.manage_guild
            ):
                return True
        raise Premium_Owner

    return commands.check(predicate)  # type: ignore[reportArgumentType]


def is_premium_user():
    def predicate(inter: disnake.CommandInteraction) -> bool:
        if Client.debug_mode:
            return True
        server = inter.bot.get_guild(Client.premium_server)
        if not server or not Client.premium_role:
            raise NotPremium
        uid = inter.author.id
        if member := server.get_member(uid):
            if member.get_role(Client.premium_role):
                return True
        raise NotPremium

    return commands.check(predicate)  # type: ignore[reportArgumentType]

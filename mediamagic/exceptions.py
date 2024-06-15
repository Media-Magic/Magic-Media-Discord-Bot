from disnake.ext import commands


class ModelOffline(Exception):
    """
    Raised When Model id offline
    """


class Premium_Owner(commands.errors.CheckFailure):
    """
    Raised when Premium User isn't the owner of the current server
    """


class NotPremium(commands.errors.CheckFailure):
    """
    Raised when User isn't premium
    """

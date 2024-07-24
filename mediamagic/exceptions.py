from disnake.ext import commands


class ModelOffline(Exception):
    """
    Raised when model id offline
    """


class Premium_Owner(commands.errors.CheckFailure):
    """
    Raised when premium user isn't the owner of the current server
    """


class NotPremium(commands.errors.CheckFailure):
    """
    Raised when user isn't premium
    """


class NotVoted(commands.errors.CheckFailure):
    """
    Raised when user didn't voted
    """

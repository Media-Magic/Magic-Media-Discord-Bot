import disnake


class DeleteButton(disnake.ui.Button):
    """Button to delete messages"""

    def __init__(
        self,
        user: int | disnake.User | disnake.Member,
        *,
        allow_manage_messages: bool = True,
        initial_message: disnake.Message | int | None = None,
        style: disnake.ButtonStyle | None = None,
        emoji: disnake.Emoji | None = None,
    ) -> None:

        super().__init__()

        if isinstance(user, int):
            user_id = user
        else:
            user_id = user.id

        self.custom_id = "DELETE"
        permissions = disnake.Permissions()
        permissions.manage_messages = allow_manage_messages
        self.custom_id += f":{permissions.value}:{user_id}:"

        if initial_message:
            if isinstance(initial_message, disnake.Message):
                initial_message = initial_message.id
            self.custom_id += str(initial_message)

        if style is None:
            if initial_message:
                self.style = disnake.ButtonStyle.danger
            else:
                self.style = disnake.ButtonStyle.secondary
        else:
            self.style = style

        if emoji is None:
            if self.style == disnake.ButtonStyle.danger:
                self.emoji = "💣"
            else:
                self.emoji = "🗑️"
        else:
            self.emoji = emoji

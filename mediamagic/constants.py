import os


class Client:
    name = "Media Magic"
    # log_config = Path("logging_config.json")
    log_file_name = "logs/debug.log"
    premium_server = int(os.getenv("PREMIUM_SERVER_ID", 1251639988811206676))
    premium_role = int(os.getenv("PREMIUM_ROLE_ID", 1251640484724609107))
    support_server_invite = os.getenv("SUPPORT_SERVER_INVITE_CODE", "sZrjFMBCYQ")
    debug_mode = False
    token = os.getenv("TOKEN")
    command_prefix = "!"
    nsfw_api = os.getenv("NSFW_API")

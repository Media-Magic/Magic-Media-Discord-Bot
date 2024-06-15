import os


class Client:
    name = "Media Magic"
    # log_config = Path("logging_config.json")
    log_file_name = "logs/debug.log"
    premium_server = 1251639988811206676
    premium_role = 1251640484724609107
    support_server_invite = "sZrjFMBCYQ"
    debug_mode = False
    token = os.getenv("TOKEN")
    command_prefix = "!"

import os
import json

from dis_snek.client import Snake
from dis_snek.models.enums import Intents
from dis_snek.models.listener import listen

from dotenv import load_dotenv

COMMAND_POST_URL = "https://discord.com/api/v8/applications/923647717375344660/commands"
COMMAND_POST_GUILD_URL = "https://discord.com/api/v8/applications/923647717375344660/guilds/367865912952619018/commands"

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
ENVTYPE = os.getenv('ENV_TYPE')

client = Snake(intents=Intents.DEFAULT)


@listen()
async def on_ready():
    print("Connected to Discord! Running in {} mode.".format(ENVTYPE))

client.grow_scale("quote")
client.start(TOKEN)

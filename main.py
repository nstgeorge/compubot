import os
import sys
import logging
import time

from dis_snek.client import Snake
from dis_snek.models.enums import Intents
from dis_snek.models.listener import listen

from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
ENVTYPE = os.getenv('ENV_TYPE')
LOGLEVEL = os.getenv("LOG_LEVEL", logging.WARNING)

if not os.path.exists('logs'):
    os.makedirs('logs')

level = getattr(logging, LOGLEVEL.upper(), logging.WARNING)
logging.basicConfig(filename='logs/compubot_{}.log'.format(time.time_ns()), filemode='w', level=level)

stdoutHandler = logging.StreamHandler(sys.stdout)
stdoutHandler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
logging.getLogger().addHandler(stdoutHandler)

COMMAND_POST_URL = "https://discord.com/api/v8/applications/923647717375344660/commands"
COMMAND_POST_GUILD_URL = "https://discord.com/api/v8/applications/923647717375344660/guilds/367865912952619018/commands"

client = Snake(intents=Intents.DEFAULT, sync_interactions=True, debug_scope=367865912952619018)


@listen()
async def on_ready():
    print("Connected to Discord! Running in {} mode.".format(ENVTYPE))

client.grow_scale("scales.quote")
client.grow_scale("scales.kill")
client.grow_scale("scales.when")
client.start(TOKEN)

import logging
import os
import sys
import time

import dis_snek
from dis_snek import Intents, Snake, listen
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
ENVTYPE = os.getenv('ENV_TYPE')
LOGLEVEL = os.getenv("LOG_LEVEL", "WARNING")

if not os.path.exists('logs'):
    os.makedirs('logs')

level = getattr(logging, LOGLEVEL.upper(), logging.WARNING)
logging.basicConfig(
    filename='logs/compubot_{}.log'.format(time.time_ns()), filemode='w', level=level)

stdoutHandler = logging.StreamHandler(sys.stdout)
stdoutHandler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
logging.getLogger().addHandler(stdoutHandler)

COMMAND_POST_URL = "https://discord.com/api/v8/applications/923647717375344660/commands"
COMMAND_POST_GUILD_URL = "https://discord.com/api/v8/applications/923647717375344660/guilds/367865912952619018/commands"

client = Snake(intents=Intents.DEFAULT, sync_interactions=True)


@listen()
async def on_ready():
    print("Connected to Discord! Running in {} mode.".format(ENVTYPE))
    print("Dis-Snek version: {}".format(dis_snek.__version__))

client.grow_scale("scales.quote")
client.grow_scale("scales.kill")
client.grow_scale("scales.when")
client.grow_scale("scales.ip")
client.grow_scale("scales.mock")
# client.grow_scale(debug_scale)

client.start(TOKEN)

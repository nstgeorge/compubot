import asyncio
import inspect
import json
import logging
import os
import random
import sys
import threading
import time

import interactions
from dotenv import load_dotenv
from openai import APITimeoutError, AsyncOpenAI, RateLimitError

load_dotenv() # Needs to be here for OpenAI
from interactions.ext.tasks import IntervalTrigger, create_task
from tenacity import retry, stop_after_attempt, wait_random_exponential

from util.chatGPT import respondWithChatGPT
from util.gptMemory import GPTMemory

# !!! NOTE TO SELF: Heroku logging is a pain. If you don't see a print(), add sys.stdout.flush() !!!

# Get environment variables
# OpenAI also requires their API key defined at OPENAI_API_KEY

ENVTYPE = os.getenv('ENV_TYPE')
TOKEN = os.getenv('DISCORD_TOKEN_TEST') if ENVTYPE == 'test' else os.getenv(
    'DISCORD_TOKEN')
LOGLEVEL = os.getenv("LOG_LEVEL", "WARNING")

MY_ID = '186691115720769536'

APPLICATION_IDS = {
    'test': '1088680993910702090',
    'prod': '923647717375344660'
}

FORTNITE_ID = '432980957394370572'

PING_WHEN_PLAYING_FORTNITE = [
    '344471073368178698',  # Jackson
    '234927911562510336'  # Colin
]

CHANNEL_TO_PING = '717977225168683090'  # rushmobies

EVERY_24_HOURS = 60 * 60 * 24

PRESENCE_OBJECTS = json.load(open("resources/bot_presence.json"))

# Set up logging

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

client = AsyncOpenAI()

# Create bot and load extensions


bot = interactions.Client(token=TOKEN)

bot.load('util.commands.ip')
bot.load('util.commands.kill')
bot.load('util.commands.locate')
bot.load('util.commands.mc')
bot.load('util.commands.mock')
bot.load('util.commands.quote')
bot.load('util.commands.when')
bot.load('util.commands.sentiment')
bot.load('util.commands.stats')


@create_task(IntervalTrigger(EVERY_24_HOURS))
async def update_presence():
    random_presence = random.choice(PRESENCE_OBJECTS)
    print("Updating presence: {}".format(random_presence['name']))
    sys.stdout.flush()
    presence = interactions.ClientPresence(
        activities=[
            interactions.PresenceActivity(
                name=random_presence['name'], type=random_presence['type'])
        ],
        status=interactions.StatusType.ONLINE,
        afk=False
    )
    await bot.change_presence(presence)

# on bot start, do stuff


@bot.event()
async def on_start():
    await update_presence()
    update_presence.start()
    print("Connected to Discord! Running in {} mode.".format(ENVTYPE))
    print("Interactions version: {}".format(interactions.__version__))
    sys.stdout.flush()

# compubot ChatGPT

memory = GPTMemory()


def sleep_log(msg):
    print('ChatGPT call failed! Retrying...')


@retry(wait=wait_random_exponential(min=1, max=5), stop=stop_after_attempt(3), reraise=True, before_sleep=sleep_log)
async def gptHandleMessage(message: interactions.Message):
    clean_content = message.content.replace(
        '<@{}>'.format(APPLICATION_IDS[ENVTYPE]), 'compubot')

    memory.append(message.channel_id, '{}: """{}"""'.format(
        message.author.username, clean_content))
    
    await respondWithChatGPT(memory=memory, message=message)


# Event handlers


@bot.event()
async def on_message_create(message: interactions.Message):
    bot_user = await bot.get_self_user()
    channel = await message.get_channel()
    if (bot_user.id in [u['id'] for u in message.mentions]
        or channel.type == interactions.ChannelType.DM) \
            and bot_user.id != message.author.id \
            and message.content:
        try:
            await gptHandleMessage(message)
        except APITimeoutError:
            print('ChatGPT API timed out.')
        except RateLimitError as err:
            print('Hit rate limit: ', err)
        except Exception as err:
            print('An unknown error has occurred: ', err)
            raise err

    if message.content and 'cock' in message.content.lower():
        await message.create_reaction('YEP:1088687844148641902')

# Check for Fortnite
last_ping = 0

@bot.event()
async def on_presence_update(activity: interactions.Presence):
    print('Got presence update for {} ({})'.format(activity.user.id, activity.activities[0].name))
    if activity.user.id in PING_WHEN_PLAYING_FORTNITE \
        and FORTNITE_ID in [a.application_id for a in activity.activities] \
        and last_ping + EVERY_24_HOURS > time.time():

        last_ping = time.time()
        await bot._http.get_channel(CHANNEL_TO_PING).send('<wakege:1045396302525120602> CRITICAL SERVER ALERT <@{}>: <@{}> is now playing Fortnite. <cringe:874735256190734337>'.format(MY_ID, activity.user.id))


# GPT commands

@bot.command(
    name="forget",
    description="make compubot forget the conversation you're having"
)
async def forget(ctx: interactions.CommandContext):
    if memory.has_conversation(ctx.channel_id):
        memory.clear(ctx.channel_id)
        await ctx.send('... What were we just talking about?')
    else:
        await ctx.send('We weren\'t talking about anything.')


@bot.command(
    name="sike",
    description="make compubot forget the last message"
)
async def sike(ctx: interactions.CommandContext):
    if memory.has_conversation(ctx.channel_id):
        memory.sike(ctx.channel_id)
        await ctx.send('... Huh?')
    else:
        await ctx.send('We weren\'t talking about anything.')


bot.start()

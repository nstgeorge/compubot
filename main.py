import json
import logging
import os
import random
import sys
import time

import interactions
from dotenv import load_dotenv
from interactions import Intents
from interactions.utils.get import get
from openai import (APITimeoutError, AsyncOpenAI, BadRequestError,
                    RateLimitError)

load_dotenv() # Needs to be here for OpenAI
from interactions.ext.tasks import IntervalTrigger, create_task
from tenacity import retry, stop_after_attempt, wait_random_exponential

from src.chatGPT import respondWithChatGPT
from src.gptMemory import memory
from src.listeners.gameRoast import roast_for_bad_game
from src.mistral import respondWithMistral
from src.moderation import flagged_by_moderation
from src.utils.describeImage import describe_image

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


bot = interactions.Client(token=TOKEN, intents=Intents.DEFAULT | Intents.GUILD_MESSAGE_CONTENT | Intents.GUILD_PRESENCES | Intents.GUILD_MEMBERS)

bot.load('src.commands.ip')
bot.load('src.commands.kill')
bot.load('src.commands.locate')
bot.load('src.commands.mc')
bot.load('src.commands.mock')
bot.load('src.commands.quote')
bot.load('src.commands.when')
bot.load('src.commands.sentiment')
bot.load('src.commands.stats')
bot.load('src.commands.imageGeneration')
bot.load('src.commands.offensiveMode')


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

async def gptHandleMessage(message: interactions.Message):
    # Check for images
    image_links = []
    if len(message.embeds) > 0 or len(message.attachments) > 0:
        image_links = [
            *[embed.url or embed.image.url for embed in message.embeds],
            *[attach.url for attach in message.attachments]
        ]
        print(image_links)
        # for url in image_links:
        #     try:
        #         img_desc = await describe_image(url, message.content)
        #         print(img_desc)
        #         memory.append(message.channel_id, "{} has uploaded an image: {}".format(message.author.username, img_desc), role="system")
        #     except BadRequestError:
        #         memory.append(message.channel_id, "{} uploaded a file that is too large (5MB max).".format(message.author.username), role="system")

    clean_content = message.content.replace(
        '<@{}>'.format(APPLICATION_IDS[ENVTYPE]), 'compubot')

    memory.append(message.channel_id, '{}: """{}"""'.format(
        message.author.username, clean_content))

    shouldGoToMistral = flagged_by_moderation(clean_content) or memory.is_offensive(message.channel_id)
    # Try ChatGPT, then skip to mistral if it fails anyway
    if not shouldGoToMistral:
        print("NON-MISTRAL CALL")
        shouldGoToMistral = await respondWithChatGPT(memory=memory, message=message, image_links=image_links)
    if shouldGoToMistral:
        print("MISTRAL CALL")
        await respondWithMistral(memory=memory, message=message)


# Event handlers

# @bot.event()
# async def on_presence_update(_, activity: interactions.Presence):
    # await roast_for_bad_game(bot, activity)

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

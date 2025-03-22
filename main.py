import json
import logging
import os
import random
import sys
import time

from dotenv import load_dotenv
from interactions import (Activity, Client, Intents, Message, Status,
                          __version__, listen, slash_command)
from interactions.api.events import MessageCreate
from interactions.ext.tasks import IntervalTrigger, create_task
from openai import APITimeoutError, AsyncOpenAI, RateLimitError

load_dotenv() # Needs to be here for OpenAI

from src.chatGPT import respondWithChatGPT
from src.gptMemory import memory
from src.mistral import respondWithMistral
from src.moderation import flagged_by_moderation

# !!! NOTE TO SELF: Heroku logging is a pain. If you don't see a print(), add sys.stdout.flush() !!!

# Get environment variables
# OpenAI also requires their API key defined at OPENAI_API_KEY

ENVTYPE = os.getenv('ENV_TYPE') or 'test'
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
bot = Client(
    token=TOKEN,
    intents=Intents.DEFAULT | Intents.GUILD_MESSAGES | Intents.GUILD_PRESENCES | Intents.GUILD_MEMBERS
)

bot.load_extension('src.commands.ip')
bot.load_extension('src.commands.kill')
bot.load_extension('src.commands.locate')
bot.load_extension('src.commands.mc')
bot.load_extension('src.commands.mock')
bot.load_extension('src.commands.quote')
bot.load_extension('src.commands.when')
bot.load_extension('src.commands.stats')
bot.load_extension('src.commands.imageGeneration')
bot.load_extension('src.commands.offensiveMode')
bot.load_extension('src.commands.voice')
bot.load_extension('src.commands.debug')


@create_task(IntervalTrigger(EVERY_24_HOURS))
async def update_presence():
    random_presence = random.choice(PRESENCE_OBJECTS)
    print("Updating presence: {}".format(random_presence['name']))
    sys.stdout.flush()
    await bot.change_presence(
        activity=Activity.create(
            name=random_presence['name'],
            type=random_presence['type']
        ),
        status=Status.ONLINE
    )

# on bot start, do stuff


@listen()
async def on_startup():
    await update_presence()
    update_presence.start()
    print("Connected to Discord! Running in {} mode.".format(ENVTYPE))
    print("Interactions version: {}".format(__version__))
    sys.stdout.flush()

# compubot ChatGPT

async def gptHandleMessage(message: Message):
    # Check for images
    image_links = []
    if message.embeds or message.attachments:
        image_links = [
            *[embed.image.url for embed in message.embeds if embed.image],
            *[attach.url for attach in message.attachments]
        ]
        print(image_links)

    clean_content = message.content.replace(
        '<@{}>'.format(APPLICATION_IDS[ENVTYPE]), 'compubot')

    memory.append(message.channel.id, '{}: """{}"""'.format(
        message.author.username, clean_content))

    shouldGoToMistral = flagged_by_moderation(clean_content) or memory.is_offensive(message.channel.id)
    # Try ChatGPT, then skip to mistral if it fails anyway
    if not shouldGoToMistral:
        print("NON-MISTRAL CALL")
        shouldGoToMistral = await respondWithChatGPT(memory=memory, message=message, image_links=image_links)
    if shouldGoToMistral:
        print("MISTRAL CALL")
        await respondWithMistral(memory=memory, message=message)


# Event handlers

@listen()
async def on_message_create(event: MessageCreate):
    message = event.message
    bot_user = bot.user
    mention_users = [user async for user in message.mention_users]
    if (bot_user.id in [u.id for u in mention_users]
        or message.channel.type == 1) \
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
        await message.add_reaction('YEP:1088687844148641902')

# GPT commands

@slash_command(
    name="forget",
    description="make compubot forget the conversation you're having"
)
async def forget(ctx):
    if memory.has_conversation(ctx.channel_id):
        memory.clear(ctx.channel_id)
        await ctx.send('... What were we just talking about?')
    else:
        await ctx.send('We weren\'t talking about anything.')


@slash_command(
    name="sike",
    description="make compubot forget the last message"
)
async def sike(ctx):
    if memory.has_conversation(ctx.channel_id):
        memory.sike(ctx.channel_id)
        await ctx.send('... Huh?')
    else:
        await ctx.send('We weren\'t talking about anything.')


bot.start()

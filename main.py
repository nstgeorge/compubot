import logging
import os
import sys
import time

import interactions
import openai
from dotenv import load_dotenv

# !!! NOTE TO SELF: Heroku logging is a pain. If you don't see a print(), add sys.stdout.flush() !!!

# Get environment variables
# OpenAI also requires their API key defined at OPENAI_API_KEY

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
ENVTYPE = os.getenv('ENV_TYPE')
LOGLEVEL = os.getenv("LOG_LEVEL", "WARNING")

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

# Create bot and load extensions

bot = interactions.Client(token=TOKEN)

bot.load('commands.ip')
bot.load('commands.kill')
bot.load('commands.locate')
bot.load('commands.mc')
bot.load('commands.mock')
bot.load('commands.quote')
bot.load('commands.when')
bot.load('commands.sentiment')

# Print on start


@bot.event()
async def on_start():
    print("Connected to Discord! Running in {} mode.".format(ENVTYPE))
    print("Interactions version: {}".format(interactions.__version__))
    sys.stdout.flush()


# compubot ChatGPT

@bot.event()
async def on_message_create(message: interactions.Message):
    print("Detected message")
    sys.stdout.flush()
    bot_user = await bot.get_self_user()
    if message.mentions and message.content:
        sys.stdout.flush()
        if bot_user.id in [u['id'] for u in message.mentions] \
                and not message.mention_everyone \
                and not message.mention_roles \
                and not message.mention_channels:

            print("I was mentioned in message")
            sys.stdout.flush()
            channel = await interactions.get(bot, interactions.Channel, object_id=message.channel_id)
            async with channel.typing:
                response = await openai.ChatCompletion.acreate(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "assistant",
                            "content": "You are compubot, a Discord bot with no useful functionality."},
                        {"role": "system",
                            "content": "Respond to all messages concisely and sarcastically."},
                        {"role": "user", "content": message.content}
                    ]
                )
            await message.reply(response.choices[0].message.content.lower())

bot.start()

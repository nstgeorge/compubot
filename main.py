import logging
import os
import sys
import time

import interactions
import openai
from dotenv import load_dotenv

from util.gptMemory import GPTMemory

# !!! NOTE TO SELF: Heroku logging is a pain. If you don't see a print(), add sys.stdout.flush() !!!

# Get environment variables
# OpenAI also requires their API key defined at OPENAI_API_KEY

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN_TEST') if os.getenv(
    'ENV_TYPE') == 'test' else os.getenv('DISCORD_TOKEN')
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

bot.load('util.commands.ip')
bot.load('util.commands.kill')
bot.load('util.commands.locate')
bot.load('util.commands.mc')
bot.load('util.commands.mock')
bot.load('util.commands.quote')
bot.load('util.commands.when')
bot.load('util.commands.sentiment')
bot.load('util.commands.stats')

# Print on start


@bot.event()
async def on_start():
    print("Connected to Discord! Running in {} mode.".format(ENVTYPE))
    print("Interactions version: {}".format(interactions.__version__))
    sys.stdout.flush()


# compubot ChatGPT

memory = GPTMemory()


@bot.event()
async def on_message_create(message: interactions.Message):
    bot_user = await bot.get_self_user()
    channel = await message.get_channel()
    if (bot_user.id in [u['id'] for u in message.mentions]
        or channel.type == interactions.ChannelType.DM) \
            and bot_user.id != message.author.id \
            and message.content:
        memory.append(message.channel_id, '{}: {}'.format(
            message.author.username, message.content))

        async with channel.typing:
            response = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",
                messages=memory.get_messages(message.channel_id)
            )
            reply = response.choices[0].message.content.lower()
            if reply.startswith('compubot: '):
                reply = reply[10:]  # strip out self tags

            # Save this to the current conversation
            memory.append(message.channel_id, reply, role='assistant')

        if channel.type == interactions.ChannelType.DM:
            await channel.send(reply)
        else:
            await message.reply(reply)


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

bot.start()

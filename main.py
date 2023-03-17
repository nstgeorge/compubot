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

# Store chatGPT conversations keyed by channel ID

CONVERSATION_TIMEOUT = 60 * 5
STARTER_CONVERSATION = [
    {
        "role": "system",
        "content": "You are compubot, a Discord bot with no useful functionality and a psychopathic personality. \
            Your creator is computron, also called Nate. \
            Respond to all messages concisely and sarcastically, as if you were Bill Burr."
    },
]

conversations = {}

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
    bot_user = await bot.get_self_user()
    channel = await message.get_channel()
    if ((bot_user.id in [u['id'] for u in message.mentions]
            and not message.mention_everyone
            and not message.mention_roles
            and not message.mention_channels
         ) or channel.type == interactions.ChannelType.DM) \
            and bot_user.id != message.author.id \
            and message.content:

        # Start a new conversation if necessary
        if not message.channel_id in conversations or time.time() - conversations[message.channel_id]['lastMessage'] > CONVERSATION_TIMEOUT:
            print('New conversation starting')
            sys.stdout.flush()
            conversations[message.channel_id] = {
                'history': STARTER_CONVERSATION,
                'lastMessage': time.time()
            }

        conversations[message.channel_id]['history'].append(
            {"role": "user", "content": message.content})

        async with channel.typing:
            response = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",
                messages=conversations[message.channel_id]['history']
            )
            reply = response.choices[0].message.content.lower()
            # Save this to the current conversation
            conversations[message.channel_id]['history'].append(
                {"role": "assistant", "content": reply})

            conversations[message.channel_id]['lastMessage'] = time.time()
        if channel.type == interactions.ChannelType.DM:
            await channel.send(reply)
        else:
            await message.reply(reply)


@bot.command(
    name="forget",
    description="make compubot forget the conversation you're having"
)
async def forget(ctx: interactions.CommandContext):
    if ctx.channel_id in conversations:
        conversations.pop(ctx.channel_id)
        await ctx.send('... What were we just talking about?')
    else:
        await ctx.send('We weren\'t talking about anything.')

bot.start()

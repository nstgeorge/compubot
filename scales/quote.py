import json
import logging
import os

from dis_snek import context_menu, CommandTypes, InteractionContext, Snake, Message, GuildText
from dis_snek.models.scale import Scale
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ENVTYPE = os.getenv('ENV_TYPE')
SETTINGS = json.load(open("resources/settings.json"))
LOGGER = logging.getLogger()
OUTPUT_CHANNEL = SETTINGS["quote"]["dev_output_channel_id"] if ENVTYPE == "dev" \
    else SETTINGS["quote"]["output_channel_id"]


class Quote(Scale):
    def __init__(self, client: Snake):
        LOGGER.debug("Initialized /quote shard")
        self.client = client

    def __message_string(self, message: Message):
        if message.content == "":
            return " - <@{}>, {}".format(message.author.id, message.timestamp)

        return "> {}\n - <@{}>, {}".format(message.content.replace("\n", "\n> "),
                                              message.author.id,
                                              message.timestamp)

    @context_menu(name="Quote", context_type=CommandTypes.MESSAGE)
    async def quote_cmd(self, ctx: InteractionContext):
        channel = await ctx.guild.get_channel(OUTPUT_CHANNEL)
        message = await ctx.channel.get_message(ctx.target_id)
        for attach in message.attachments:
            await channel.send(attach.url)
        await channel.send(self.__message_string(message))
        await ctx.send(SETTINGS["quote"]["success_message"])
        LOGGER.debug("quote: Sent quote {}".format(message.id))

    @quote_cmd.error
    async def command_error(self, e, *args, **kwargs):
        LOGGER.error("quote: Quote command error: {}".format(e))


def setup(bot):
    Quote(bot)

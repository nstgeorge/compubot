import json
import logging
import os
from pathlib import Path

from dis_snek import (CommandTypes, InteractionContext, Message, Scale, Snake,
                      context_menu)
from dotenv import load_dotenv

load_dotenv()

ENVTYPE = os.getenv('ENV_TYPE')
SETTINGS = json.load(open("resources/settings.json"))
LOGGER = logging.getLogger()


class Quote(Scale):
    def __init__(self, client: Snake):
        LOGGER.debug("Initialized /quote shard")
        self.client = client

    def __get_output_channel(self, ctx: InteractionContext):
        if ENVTYPE == "dev" and ctx.author.id in SETTINGS["global"]["admin_ids"]:
            return SETTINGS["quote"]["dev_output_channel_id"]
        else:
            return SETTINGS["quote"]["output_channel_id"]

    def __message_string(self, message: Message):
        if message.content == "":
            return " - <@{}>, {}".format(message.author.id, message.timestamp)

        return "> {}\n - <@{}>, {}".format(message.content.replace("\n", "\n> "),
                                           message.author.id,
                                           message.timestamp)

    @context_menu(name="Quote", context_type=CommandTypes.MESSAGE)
    async def quote_cmd(self, ctx: InteractionContext):
        channel = await ctx.guild.get_channel(self.__get_output_channel(ctx))
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

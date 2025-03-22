import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from interactions import (Client, CommandType, ContextMenuContext, Extension,
                          GuildText, Message, context_menu, listen)

load_dotenv()

ENVTYPE = os.getenv('ENV_TYPE')
SETTINGS = json.load(open("resources/settings.json"))
LOGGER = logging.getLogger()


class Quote(Extension):
    def __init__(self, client: Client):
        LOGGER.debug("Initialized /quote shard")
        self.client = client

    def __get_output_channel(self, ctx: ContextMenuContext):
        if ENVTYPE == "dev" and ctx.author.id in SETTINGS["global"]["admin_ids"]:
            return SETTINGS["quote"]["dev_output_channel_id"]
        else:
            return SETTINGS["quote"]["output_channel_id"]

    def __message_string(self, message: Message):
        if not message.content:
            return " - <@{}>, {}".format(message.author.id, message.timestamp)

        return "> {}\n - <@{}>, {}".format(message.content.replace("\n", "\n> "),
                                           message.author.id,
                                           message.timestamp)

    @context_menu(name="Quote", context_type=CommandType.MESSAGE)
    async def quote_cmd(self, ctx: ContextMenuContext):
        channel = await self.client.fetch_channel(self.__get_output_channel(ctx))
        if not isinstance(channel, GuildText):
            await ctx.respond("Error: Output channel must be a text channel")
            return
        
        if isinstance(ctx.target, Message):
            message = await ctx.target.fetch_referenced_message()
            if not message:
                await ctx.respond("Error: Could not fetch message")
                return

            for attach in message.attachments:
                await channel.send(attach.url)
            await channel.send(self.__message_string(message))
            await ctx.respond(SETTINGS["quote"]["success_message"])
            LOGGER.debug("quote: Sent quote {}".format(message.id))

    @listen()
    async def on_command_error(self, event):
        LOGGER.error("quote: Quote command error: {}".format(event.error))


def setup(bot):
    Quote(bot)

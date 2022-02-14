import json
import logging
import os
from random import choice

from dis_snek import (CommandTypes, InteractionContext, Message, Scale, Snake,
                      context_menu)
from dotenv import load_dotenv

load_dotenv()

ENVTYPE = os.getenv('ENV_TYPE')
LOGGER = logging.getLogger()


class Mock(Scale):
    def __init__(self, client: Snake):
        LOGGER.debug("Initialized /mock shard")
        self.client = client

    def __mock_text(self, text: str):
        return ''.join(choice((str.upper, str.lower))(c) for c in text)

    @context_menu(name="Mock", context_type=CommandTypes.MESSAGE)
    async def quote_cmd(self, ctx: InteractionContext):
        message = await ctx.channel.get_message(ctx.target_id)
        await ctx.send("\"{}\"".format(self.__mock_text(message.content)))
        LOGGER.debug("mock: mocked \"{}\"".format(message.id))

    @quote_cmd.error
    async def command_error(self, e, *args, **kwargs):
        LOGGER.error("mock: Mock command error: {}".format(e))


def setup(bot):
    Mock(bot)

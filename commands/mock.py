import json
import logging
import os
from random import choice

import interactions
from dotenv import load_dotenv

load_dotenv()

ENVTYPE = os.getenv('ENV_TYPE')
LOGGER = logging.getLogger()


class Mock(interactions.Extension):
    def __init__(self, client: interactions.Client):
        LOGGER.debug("Initialized /mock shard")
        self.client = client

    def __mock_text(self, text: str):
        return ''.join(choice((str.upper, str.lower))(c) for c in text)

    @interactions.extension_message_command(name="Mock")
    async def mock_cmd(self, ctx: interactions.CommandContext):
        message = await ctx.channel.get_message(ctx.target_id)
        await ctx.send("\"{}\"".format(self.__mock_text(message.content)))
        LOGGER.debug("mock: mocked \"{}\"".format(message.id))

    @mock_cmd.error
    async def command_error(self, e, *args, **kwargs):
        LOGGER.error("mock: Mock command error: {}".format(e))


def setup(bot):
    Mock(bot)

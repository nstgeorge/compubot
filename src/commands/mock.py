import logging
import os
from random import choice

from dotenv import load_dotenv
from interactions import Client, Extension, SlashContext, slash_command

load_dotenv()

ENVTYPE = os.getenv('ENV_TYPE')
LOGGER = logging.getLogger()


class Mock(Extension):
    def __init__(self, client: Client):
        LOGGER.debug("Initialized /mock shard")
        self.client = client

    def __mock_text(self, text: str):
        return ''.join(choice((str.upper, str.lower))(c) for c in text)

    @slash_command(name="mock")
    async def mock_cmd(self, ctx: SlashContext):
        message = ctx.message
        if message is not None:
            await ctx.send("\"{}\"".format(self.__mock_text(message.content)))
            LOGGER.debug("mock: mocked \"{}\"".format(message.id))
        else:
            await ctx.send("What are you trying to mock?")

    @mock_cmd.error
    async def command_error(self, e, *args, **kwargs):
        LOGGER.error("mock: Mock command error: {}".format(e))


def setup(bot):
    Mock(bot)

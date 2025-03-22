import json
import logging

import interactions
from interactions import (Client, Extension, OptionType, SlashContext,
                          slash_command, slash_option)

USER_PHRASES = json.load(open("resources/when_users.json"))
LOGGER = logging.getLogger()


class When(Extension):
    def __init__(self, client: Client):
        LOGGER.debug("Initialized /when shard")
        self.client = client

    @slash_command(
        name="when",
        description="when will the regulars be on?"
    )
    @slash_option(
        name="user",
        description="let's find out when this person is on",
        required=True,
        opt_type=OptionType.MENTIONABLE
    )
    async def when(self, ctx: SlashContext, user: interactions.Member):
        if str(user.id) in USER_PHRASES.keys():
            await ctx.send("<@{}> will be on {}".format(user.id, USER_PHRASES[str(user.id)]))
        else:
            await ctx.send("I don't know.")


def setup(bot):
    When(bot)

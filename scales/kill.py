import json
import random
import logging

from dis_snek import InteractionContext, OptionTypes, Snake, slash_command, slash_option, MentionTypes
from dis_snek.models.scale import Scale

import want_words as ww

SETTINGS = json.load(open("resources/settings.json"))
LOGGER = logging.getLogger()


class Kill(Scale):
    def __init__(self, client: Snake):
        LOGGER.debug("Initialized /kill shard")
        self.client = client

    @slash_command(name="kill", description="ruthlessly murder your friends")
    @slash_option(
        name="user",
        description="tag who you want dead",
        required=True,
        opt_type=OptionTypes.MENTIONABLE
    )
    async def kill(self, ctx: InteractionContext, user: MentionTypes.USERS):
        scope = {
            "name": f"<@{user.id}>",
            "caller_name": f"@<{ctx.author.id}>",
        }
        if user.id in SETTINGS["global"]["admin_ids"]:
            await ctx.send(ww.resolve("{msg_kill_admin}", scope))
        else:
            await ctx.send(ww.resolve("{msg_kill}", scope))
        LOGGER.debug("kill: {} killed {}".format(ctx.author.id, user.id))


def setup(bot):
    Kill(bot)

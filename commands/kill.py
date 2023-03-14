import json
import logging
import random

import interactions

KILL_PHRASES = json.load(open("resources/kill_strings.json"))
KILL_PHRASES_VS_ADMIN = json.load(
    open("resources/kill_strings_against_admin.json"))
SETTINGS = json.load(open("resources/settings.json"))
LOGGER = logging.getLogger()


class Kill(interactions.Extension):
    def __init__(self, client: interactions.Client):
        LOGGER.debug("Initialized /kill shard")
        self.client = client

    @interactions.extension_command(
        name="kill",
        description="ruthlessly murder your friends",
        options=[
            interactions.Option(
                name="user",
                description="tag who you want dead",
                required=True,
                type=interactions.OptionType.MENTIONABLE
            )
        ]
    )
    async def kill(self, ctx: interactions.CommandContext, user: interactions.AllowedMentionType.USERS):
        if user.id in SETTINGS["global"]["admin_ids"]:
            await ctx.send(
                random.choice(KILL_PHRASES_VS_ADMIN)
                .replace("{name}", "<@{}>".format(user.id))
                .replace("{caller_name}", "<@{}>".format(ctx.author.id))
            )
        else:
            await ctx.send(random.choice(KILL_PHRASES)
                           .replace("{name}", "<@{}>".format(user.id))
                           .replace("{caller_name}", "<@{}>".format(ctx.author.id)))
        LOGGER.debug("kill: {} killed {}".format(ctx.author.id, user.id))


def setup(bot):
    Kill(bot)

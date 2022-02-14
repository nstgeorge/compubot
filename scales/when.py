import json
import logging

from dis_snek import (InteractionContext, MentionTypes, OptionTypes, Scale,
                      Snake, slash_command, slash_option)

USER_PHRASES = json.load(open("resources/when_users.json"))
LOGGER = logging.getLogger()


class When(Scale):
    def __init__(self, client: Snake):
        LOGGER.debug("Initialized /when shard")
        self.client = client

    @slash_command(name="when", description="when will the regulars be on?")
    @slash_option(
        name="user",
        description="let's find out when this person is on",
        required=True,
        opt_type=OptionTypes.MENTIONABLE
    )
    async def when(self, ctx: InteractionContext, user: MentionTypes.USERS):
        if str(user.id) in USER_PHRASES.keys():
            await ctx.send("<@{}> will be on {}".format(user.id, USER_PHRASES[str(user.id)]))
        else:
            await ctx.send("I don't know.")


def setup(bot):
    When(bot)

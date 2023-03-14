import json
import logging

import interactions

USER_PHRASES = json.load(open("resources/when_users.json"))
LOGGER = logging.getLogger()


class When(interactions.Extension):
    def __init__(self, client: interactions.Client):
        LOGGER.debug("Initialized /when shard")
        self.client = client

    @interactions.extension_command(
        name="when",
        description="when will the regulars be on?",
        options=[
            interactions.Option(
                name="user",
                description="let's find out when this person is on",
                required=True,
                type=interactions.OptionType.MENTIONABLE
            )
        ]
    )
    async def when(self, ctx: interactions.CommandContext, user: interactions.AllowedMentionType.USERS):
        if str(user.id) in USER_PHRASES.keys():
            await ctx.send("<@{}> will be on {}".format(user.id, USER_PHRASES[str(user.id)]))
        else:
            await ctx.send("I don't know.")


def setup(bot):
    When(bot)

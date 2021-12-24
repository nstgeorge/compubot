import json
import random

from dis_snek import InteractionContext, OptionTypes, Snake, slash_command, slash_option, MentionTypes
from dis_snek.models.scale import Scale

KILL_PHRASES = json.load(open("resources/kill_strings.json"))
KILL_PHRASES_VS_ADMIN = json.load(open("resources/kill_strings_against_admin.json"))
SETTINGS = json.load(open("resources/settings.json"))


class Kill(Scale):
    def __init__(self, client: Snake):
        self.client = client

    @slash_command(name="kill", description="ruthlessly murder your friends")
    @slash_option(
        name="user",
        description="tag who you want dead",
        required=True,
        opt_type=OptionTypes.MENTIONABLE
    )
    async def kill(ctx: InteractionContext, user: MentionTypes.USERS):
        if user.id in SETTINGS["global"]["admin_ids"]:
            await ctx.send(random.choice(
                KILL_PHRASES_VS_ADMIN.replace("{name}", user).replace("{caller_name}", ctx.author.id)
            ))
        await ctx.send(random.choice(KILL_PHRASES.replace("{name}", user).replace("{caller_name}", ctx.author.id)))

def setup(bot):
    Kill(bot)

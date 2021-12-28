import logging
import itertools
import random
import json
import time

from dis_snek import InteractionContext, OptionTypes, Snake, slash_command, slash_option, MentionTypes
from dis_snek.models.scale import Scale

LOGGER = logging.getLogger()
IP_PHRASES = json.load(open("resources/ip_strings.json"))
SETTINGS = json.load(open("resources/settings.json"))

class IP(Scale):
    def __init__(self, client: Snake):
        LOGGER.debug("Initialized /ip shard")
        self.client = client
        self.__spinner = itertools.cycle(["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"])

    def __message_text(self, spinner, message):
        return "{} {}".format(spinner, message)

    def __gen_user_ip(self, user: MentionTypes.USERS):
        r = random.Random(user.id)
        return "{}.{}.{}.{}".format(r.randrange(10, 99, 1),
                                    r.randrange(10, 99, 1),
                                    r.randrange(100, 999, 1),
                                    r.randrange(100, 999, 1))

    @slash_command(name="ip", description="really truly hack a person")
    @slash_option(
        name="user",
        description="your unfortunate target",
        required=True,
        opt_type=OptionTypes.MENTIONABLE
    )
    async def ip(self, ctx: InteractionContext, user: MentionTypes.USERS):
        texts = random.sample(IP_PHRASES, SETTINGS["ip"]["messages_per_request"])
        msg = await ctx.send("Beginning hack...")
        time.sleep(1)

        for text in texts:
            for i in range(3):
                spinner = next(self.__spinner)
                await msg.edit(self.__message_text(spinner, text))
                time.sleep(0.7)

        await msg.edit("Hack complete. <@{}>'s IP: {}".format(user.id, self.__gen_user_ip(user)))


def setup(bot):
    IP(bot)

import itertools
import json
import logging
import random
import time

import interactions

LOGGER = logging.getLogger()
IP_PHRASES = json.load(open("resources/ip_strings.json"))
SETTINGS = json.load(open("resources/settings.json"))


class IP(interactions.Extension):
    def __init__(self, client: interactions.Client):
        LOGGER.debug("Initialized /ip shard")
        self.client = client
        self.__spinner = itertools.cycle(
            ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"])

    def __message_text(self, spinner, message):
        return "{} {}".format(spinner, message)

    def __gen_user_ip(self, user: interactions.AllowedMentionType.USERS):
        r = random.Random(user.id)
        return "{}.{}.{}.{}".format(r.randrange(1, 255, 1),
                                    r.randrange(1, 255, 1),
                                    r.randrange(1, 255, 1),
                                    r.randrange(1, 255, 1))

    def __gen_google_maps_url(self):
        # r = random.Random(user.id)
        return "https://www.google.com/maps/@{},{},12z".format(random.uniform(-90, 90), random.uniform(-180, 180))

    @interactions.extension_command(
        name="ip",
        description="really truly hack a person",
        options=[
            interactions.Option(
                name="user",
                description="your unfortunate target",
                required=True,
                type=interactions.OptionType.MENTIONABLE
            )
        ]
    )
    async def ip(self, ctx: interactions.CommandContext, user: interactions.AllowedMentionType.USERS):
        texts = random.sample(
            IP_PHRASES, SETTINGS["ip"]["messages_per_request"])
        msg = await ctx.send("Beginning hack...")
        time.sleep(1)

        for text in texts:
            for i in range(3):
                spinner = next(self.__spinner)
                await msg.edit(self.__message_text(spinner, text))
                time.sleep(0.7)

        await msg.edit("Hack complete. \n<@{}>'s IP: {} \nLocation: {}".format(
            user.id, self.__gen_user_ip(user), self.__gen_google_maps_url()))


def setup(bot):
    IP(bot)

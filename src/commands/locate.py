import json
import logging
import os

import requests
from interactions import (Client, Extension, OptionType, SlashContext,
                          slash_command, slash_option)

SETTINGS = json.load(open("resources/settings.json"))
LOGGER = logging.getLogger()
IP_GEOLOCATION_KEY = os.getenv('IP_GEOLOCATION_KEY')


def gen_google_maps_url(x, y):
    return "https://www.google.com/maps/search/?api=1&query={},{}".format(x, y)


class Locate(Extension):
    def __init__(self, client: Client):
        LOGGER.debug("Initialized /locate shard")
        self.client = client

    @slash_command(
        name="locate",
        description="geolocate an IP address (THIS IS REAL, NOT A JOKE)"
    )
    @slash_option(
        name="ip",
        description="ip to locate",
        required=True,
        opt_type=OptionType.STRING
    )
    async def locate(self, ctx: SlashContext, ip: str):
        await ctx.defer()

        response = requests.get(
            "https://api.ipgeolocation.io/ipgeo?apiKey={}&ip={}".format(IP_GEOLOCATION_KEY, ip))
        response_data = response.json()

        if response.ok:
            g_map = gen_google_maps_url(
                response_data['latitude'],
                response_data['longitude']
            )
            await ctx.send('{} is registered in {}, {}. Here\'s the map: {}'.format(ip, response_data['city'], response_data['country_name'], g_map))
        else:
            await ctx.send('Couldn\'t locate {}. Maybe try again and be better this time?'.format(ip))

        LOGGER.debug("locate: {} tried to locate {}".format(ctx.author.id, ip))


def setup(bot):
    Locate(bot)

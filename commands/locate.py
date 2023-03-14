import json
import logging
import os

import interactions
import requests

KILL_PHRASES = json.load(open("resources/kill_strings.json"))
KILL_PHRASES_VS_ADMIN = json.load(
    open("resources/kill_strings_against_admin.json"))
SETTINGS = json.load(open("resources/settings.json"))
LOGGER = logging.getLogger()
M3O_TOKEN = os.getenv('M3O_TOKEN')


def gen_google_maps_url(x, y):
    return "https://www.google.com/maps/search/?api=1&query={},{}".format(x, y)


class Locate(interactions.Extension):
    def __init__(self, client: interactions.Client):
        LOGGER.debug("Initialized /locate shard")
        self.client = client

    @interactions.extension_command(
        name="locate",
        description="geolocate an IP address (THIS IS REAL, NOT A JOKE)",
        options=[
            interactions.Option(
                name="ip",
                description="ip to locate",
                required=True,
                type=interactions.OptionType.STRING
            )
        ]
    )
    async def locate(self, ctx: interactions.CommandContext, ip: str):
        msg = await ctx.send('Locating...')
        headers = {
            'Authorization': 'Bearer {}'.format(M3O_TOKEN)
        }
        data = {
            'ip': ip
        }
        response = requests.post(
            "https://api.m3o.com/v1/ip/Lookup", json=data, headers=headers)
        response_data = response.json()
        if response.ok:
            g_map = gen_google_maps_url(
                response_data['latitude'], response_data['longitude'])
            await msg.edit('{} is registered in {}, {}. Here\'s the map: {}'.format(ip, response_data['city'],
                                                                                    response_data['country'],
                                                                                    g_map))
        else:
            await msg.edit('Couldn\'t locate {}. Maybe try again and be better this time?'.format(ip))
        LOGGER.debug("locate: {} tried to locate {}".format(ctx.author.id, ip))


def setup(bot):
    Locate(bot)

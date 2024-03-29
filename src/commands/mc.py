import json
import logging

import interactions
from mcstatus import JavaServer

SETTINGS = json.load(open("resources/settings.json"))
LOGGER = logging.getLogger()

QUICK_REFERENCE = {
    'ea': 'cloud.elysiumalchemy.com',
    '': 'cloud.elysiumalchemy.com'
}

# Handle a request from natural language


def get_status_handle(memory, message, ip: str):
    return get_status(ip)


def get_status(ip: str):
    if not ip:
        ip = 'cloud.elysiumalchemy.com'
    if ip in QUICK_REFERENCE.keys():
        ip = QUICK_REFERENCE[ip]
    server = JavaServer.lookup(ip)
    status, query = None, None

    try:
        status = server.status()
    except TimeoutError:
        return 'Timed out while checking {}.'.format(ip)

    try:
        query = server.query()
    except TimeoutError:
        return 'The server isn\'t accepting queries, but it\'s online!'

    if status.players.sample or hasattr(query, 'names'):
        return (
            '{} has {}/{} players online. Here\'s who is on: \n{}'.format(
                ip,
                status.players.online,
                status.players.max,
                ', '.join(query.players.names or [
                    p.name for p in status.players.sample])
            )
        )
    else:
        return (
            '{} has {}/{} players online.'.format(
                ip,
                status.players.online,
                status.players.max
            )
        )


class Minecraft(interactions.Extension):
    def __init__(self, client: interactions.Client):
        LOGGER.debug("Initialized /mc shard")
        self.client = client

    @interactions.extension_command(
        name="mc",
        description="check the status of a minecraft server",
        options=[
            interactions.Option(
                name="ip",
                description="ip or hostname of the server",
                required=True,
                type=interactions.OptionType.STRING
            )
        ]
    )
    async def mc_status(self, ctx: interactions.CommandContext, ip: str):
        msg = await ctx.send('Just a second...')
        status_str = get_status(ip)

        await msg.edit(status_str)

        LOGGER.debug(
            "mc_status: {} checked the status of {}".format(ctx.author.id, ip))


def setup(bot):
    Minecraft(bot)

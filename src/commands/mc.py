import json
import logging

from interactions import (Client, Extension, OptionType, SlashContext,
                          slash_command, slash_option)
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

    player_names = []
    if query and hasattr(query, 'players') and hasattr(query.players, 'names'):
        player_names = query.players.names
    elif status.players.sample:
        player_names = [p.name for p in status.players.sample]

    if player_names:
        return (
            '{} has {}/{} players online. Here\'s who is on: \n{}'.format(
                ip,
                status.players.online,
                status.players.max,
                ', '.join(player_names)
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


class Minecraft(Extension):
    def __init__(self, client: Client):
        LOGGER.debug("Initialized /mc shard")
        self.client = client

    @slash_command(
        name="mc",
        description="check the status of a minecraft server"
    )
    @slash_option(
        name="ip",
        description="ip or hostname of the server",
        required=True,
        opt_type=OptionType.STRING
    )
    async def mc_status(self, ctx: SlashContext, ip: str):
        await ctx.defer()
        status_str = get_status(ip)
        await ctx.send(status_str)
        LOGGER.debug(
            "mc_status: {} checked the status of {}".format(ctx.author.id, ip))


def setup(bot):
    Minecraft(bot)

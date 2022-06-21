import json
import logging
from mcstatus import JavaServer

from dis_snek import (InteractionContext, MentionTypes, OptionTypes, Scale,
                      Snake, slash_command, slash_option)


SETTINGS = json.load(open("resources/settings.json"))
LOGGER = logging.getLogger()

QUICK_REFERENCE = {
    'ea': 'cloud.elysiumalchemy.com',
    '': 'cloud.elysiumalchemy.com'
}

class Minecraft(Scale):
    def __init__(self, client: Snake):
        LOGGER.debug("Initialized /mc shard")
        self.client = client

    @slash_command(name="mc", description="check the status of a minecraft server")
    @slash_option(
        name="ip",
        description="ip or hostname of the server",
        required=True,
        opt_type=OptionTypes.STRING
    )
    async def mc_status(self, ctx: InteractionContext, ip: str):
        if ip in QUICK_REFERENCE.keys():
            ip = QUICK_REFERENCE[ip]
        server = JavaServer.lookup(ip)
        status, query = None, None
        msg = await ctx.send('Just a second...')
        try:
            status = server.status()
        except TimeoutError:
            await msg.edit('Timed out while checking {}. Did you type the right hostname and port?'.format(ip))
            return
        try:
            query = server.query()
        except TimeoutError:
            # Server isn't accepting queries. That's okay :)
            pass
        if status.players.sample or hasattr(query, 'names'):
            await msg.edit(
                '{} has {}/{} players online. Here\'s who is on: \n{}'.format(
                    ip,
                    status.players.online,
                    status.players.max,
                    ', '.join(query.players.names or [p.name for p in status.players.sample])
                )
            )
        else:
            await msg.edit(
                '{} has {}/{} players online.'.format(
                    ip,
                    status.players.online,
                    status.players.max
                )
            )

        LOGGER.debug("mc_status: {} checked the status of {}".format(ctx.author.id, ip))


def setup(bot):
    Minecraft(bot)

import json
import logging
import os
import sys

import interactions
from riotwatcher import ApiError, LolWatcher

LOGGER = logging.getLogger()

REGION = os.getenv('RIOT_REGION')
RIOT_LEAGUE_KEY = os.getenv('RIOT_LEAGUE_KEY')


class Rank(interactions.Extension):
    def __init__(self, client: interactions.Client):
        LOGGER.debug("Initialized /rank shard")
        self.client = client
        self.lol_watcher = LolWatcher(RIOT_LEAGUE_KEY, default_status_v4=True)

    @interactions.extension_command(
        name="rank"
    )
    async def rank(self, ctx: interactions.CommandContext):
        pass

    @rank.subcommand(
        name='league',
        description='get someone\'s league rank (cringe)',
        options=[
            interactions.Option(
                name="summoner",
                description="summoner name to check",
                required=True,
                type=interactions.OptionType.STRING
            )
        ]
    )
    async def league(self, ctx: interactions.CommandContext, summoner: str):
        msg = await ctx.send('Looking for data on {}...'.format(summoner))
        try:
            summoner_data = self.lol_watcher.summoner.by_name(REGION, summoner)
            rank_data = self.lol_watcher.league.by_summoner(
                REGION, summoner_data['id'])[0]
            print(rank_data)
            await msg.edit('{} is {} {} ({} wins, {} losses).'.format(summoner, rank_data['tier'], rank_data['rank'], rank_data['wins'], rank_data['losses']))
        except ApiError:
            print('No data found for {}'.format(summoner))
            await msg.edit('I couldn\'t find a summoner named {}.'.format(summoner))
        sys.stdout.flush()


def setup(bot):
    Rank(bot)

import json
import logging
import os
import sys

import interactions
from riotwatcher import ApiError, LolWatcher

from src.TrackerGG import TrackerGG

LOGGER = logging.getLogger()

REGION = os.getenv('RIOT_REGION')
RIOT_LEAGUE_KEY = os.getenv('RIOT_LEAGUE_KEY')
TRACKER_GG_KEY = os.getenv('TRACKER_GG_KEY')


class Stats(interactions.Extension):
    def __init__(self, client: interactions.Client):
        LOGGER.debug("Initialized /rank shard")
        self.client = client
        self.lol_watcher = LolWatcher(RIOT_LEAGUE_KEY, default_status_v4=True)
        self.tracker_gg = TrackerGG(TRACKER_GG_KEY)

    @interactions.extension_command(
        name="stats"
    )
    async def stats(self, ctx: interactions.CommandContext):
        pass

    @stats.subcommand(
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
        channel = await ctx.get_channel()
        async with channel.typing:
            try:
                summoner_data = self.lol_watcher.summoner.by_name(
                    REGION, summoner)
                rank_data = self.lol_watcher.league.by_summoner(
                    REGION, summoner_data['id'])
                if (len(rank_data) == 0):
                    await ctx.send('{} is not ranked this season.'.format(summoner))
                    return
                rank_data = rank_data[0]
                await ctx.send('{} is {} {} ({} wins, {} losses).'.format(summoner, rank_data['tier'], rank_data['rank'], rank_data['wins'], rank_data['losses']))
            except ApiError:
                print('No data found for {}'.format(summoner))
                await ctx.send('I couldn\'t find a summoner named {}.'.format(summoner))
            sys.stdout.flush()

    @stats.subcommand(
        name='csgo',
        description='get someone\'s CS:GO stats',
        options=[
            interactions.Option(
                name="username",
                description="Steam ID/username",
                required=True,
                type=interactions.OptionType.STRING
            )
        ]
    )
    async def csgo(self, ctx: interactions.CommandContext, username: str):
        channel = await ctx.get_channel()
        async with channel.typing:
            try:
                stats = self.tracker_gg.get_player_stats(username)['data']
                if stats:
                    await ctx.send(self._format_csgo_stats_string(username, stats))
                    return
                else:
                    await ctx.send('Could not get stats for {}.'.format(username))
                    return
            except Exception as e:
                await ctx.send(e.args[0])

    def _format_csgo_stats_string(self, username, stats):
        main_segment = next(
            segment for segment in stats['segments'] if segment['metadata']['name'] == 'Lifetime')['stats']

        return f"** {username} ({stats['platformInfo']['platformUserHandle']}) CS:GO Statistics**\n\n\
>>> **----- General -----**\n\
**Play time**: {main_segment['timePlayed']['displayValue']} ({main_segment['timePlayed']['percentile']} percentile) \n\
**Kills**: {main_segment['kills']['displayValue']} ({main_segment['kills']['percentile']} percentile) \n\
**Deaths**: {main_segment['deaths']['displayValue']} ({main_segment['deaths']['percentile']} percentile) \n\
**K/D**: {main_segment['kd']['displayValue']} ({main_segment['kd']['percentile']} percentile) \n\
**Headshot Percentage**: {main_segment['headshotPct']['displayValue']} ({main_segment['headshotPct']['percentile']} percentile) \n\
**Accuracy**: {main_segment['shotsAccuracy']['displayValue']} ({main_segment['shotsAccuracy']['percentile']} percentile) \n\n\
 **----- Competitive -----**\n\
**Round Wins**: {main_segment['roundsWon']['displayValue']} ({main_segment['roundsWon']['percentile']} percentile) \n\
**Round Losses**: {main_segment['losses']['displayValue']} ({main_segment['losses']['percentile']} percentile) \n\
**W/L Percentage**: {main_segment['wlPercentage']['displayValue']} ({main_segment['wlPercentage']['percentile']} percentile)"


def setup(bot):
    Stats(bot)

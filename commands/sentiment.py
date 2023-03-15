import json
import logging
import os
import random

import interactions
import requests

PHRASES = json.load(open("resources/sentiment_strings.json"))
SETTINGS = json.load(open("resources/settings.json"))
LOGGER = logging.getLogger()
M3O_TOKEN = os.getenv('M3O_TOKEN')


class Sentiment(interactions.Extension):
    def __init__(self, client: interactions.Client):
        LOGGER.debug("Initialized /sentiment shard")
        self.client = client

    @interactions.extension_message_command(name="Sentiment")
    async def locate(self, ctx: interactions.CommandContext):
        msg = await ctx.send('> {}\nAnalyzing...'.format(ctx.target.content))
        headers = {
            'Authorization': 'Bearer {}'.format(M3O_TOKEN)
        }
        data = {
            'text': ctx.target.content
        }

        response = requests.post(
            "https://api.m3o.com/v1/sentiment/Analyze", json=data, headers=headers)
        response_data = response.json()

        if response.ok:
            await msg.edit('> {}\nSentiment analysis results: {}'.format(
                ctx.target.content,
                random.choice(
                    PHRASES['positive'] if response_data['score'] == 1 else PHRASES['negative']
                )
            ))
        else:
            await msg.edit('Unable to analyze this text. Try again later, maybe.')

        LOGGER.debug("sentiment run")


def setup(bot):
    Sentiment(bot)

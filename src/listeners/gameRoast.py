import os
import random
import time
from typing import Dict

from dotenv import load_dotenv
from interactions import Client, Extension, GuildText, Snowflake, listen
from interactions.api.events import PresenceUpdate

from src.gptMemory import memory
from src.mistral import oneOffResponseMistral

load_dotenv()

ENVTYPE = os.getenv('ENV_TYPE')

BASE_ROAST_PROBABILITY = 10 # out of 100
DAYS_TO_100_PROBABILITY = 3 # timescale to increase roast probability by

SECS_PER_DAY = 60 * 60 * 24
AVOID_SPAM_COOLDOWN = SECS_PER_DAY / 2

GAME_IDS: Dict[str, str] = {
  '432980957394370572': 'Fortnite',
  '356876590342340608': 'Rainbow Six Siege',
  '356869127241072640': 'League of Legends',
  '356877880938070016': 'Rocket League',
  '357607478105604096': 'War Thunder',
  '1205090671527071784': 'Helldivers',
  '1116835216464543946': 'Phasmophobia',
  '363445589247131668': 'Roblox',
  '1158877933042143272': 'Counter-Strike 2'
}

PING_WHEN_PLAYING: Dict[str, Dict[str, float]] = {
  '344471073368178698': {
    'last_ping': time.time()
  },  # Jackson
  '234927911562510336': {
    'last_ping': time.time()
  },  # Colin
  '151856792224268288': {
    'last_ping': time.time()
  }, # Kobe
  '238465524550467585': {
    'last_ping': time.time()
  }, # Jacob
  '186691115720769536': {
    'last_ping': time.time()
  } # Me
}

CHANNEL_TO_PING = Snowflake(1086455598784188496) if ENVTYPE == 'prod' else Snowflake(923800790148202509)  # talk-to-compubot or test channel

def roast_probability(user_meta: Dict[str, float]) -> float:
  return (
    BASE_ROAST_PROBABILITY + (
      (time.time() - user_meta['last_ping'])
        / (SECS_PER_DAY * DAYS_TO_100_PROBABILITY)
      ) * (100 - BASE_ROAST_PROBABILITY))

class GameRoast(Extension):
    def __init__(self, client: Client):
        self.client = client

    @listen()
    async def on_presence_update(self, event: PresenceUpdate) -> None:
        if not event.activities:
            return

        matches = list(set(GAME_IDS) & set([str(getattr(a, 'application_id', None)) for a in event.activities if getattr(a, 'application_id', None)]))
        if not matches or str(event.user.id) not in PING_WHEN_PLAYING:
            return

        match_id = matches[0]
        user_meta = PING_WHEN_PLAYING[str(event.user.id)]
        
        # Check spam cooldown and roast probability
        print("probability: {}".format(roast_probability(user_meta)))
        print("cooldown: {} {} ({})".format(
          user_meta['last_ping'] + AVOID_SPAM_COOLDOWN,
          time.time(),
          user_meta['last_ping'] + AVOID_SPAM_COOLDOWN < time.time()
        ))

        if user_meta['last_ping'] + AVOID_SPAM_COOLDOWN < time.time() \
          and random.randrange(0, 100) <= roast_probability(user_meta):
            
            channel = await self.client.fetch_channel(CHANNEL_TO_PING)
            if not isinstance(channel, GuildText):
                return

            async with channel.typing:
                activity_name = next((getattr(a, 'name', 'Unknown Game') for a in event.activities if str(getattr(a, 'application_id', None)) == match_id), "Unknown Game")
                print('Got roastable presence update for {} ({})'.format(
                    event.user.id, 
                    activity_name
                ))
                
                PING_WHEN_PLAYING[str(event.user.id)]['last_ping'] = time.time()
                
                # Re-generate responses until it includes the user's tag
                max_retries = 5
                attempt = 1
                response = ""
                while '<@{}>'.format(event.user.id) not in response and attempt <= max_retries:
                    response = await oneOffResponseMistral(
                        "<@{}> is now playing {}. Roast them mercilessly and creatively. Say their name in the message.".format(
                            event.user.id, 
                            GAME_IDS[match_id]
                        ), 
                        role="user"
                    )
                    if not response:
                        response = ""
                    print(response)
                    attempt += 1
                
                memory.append(CHANNEL_TO_PING, response, role="system")
                await channel.send(response)

def setup(bot: Client) -> None:
    GameRoast(bot)
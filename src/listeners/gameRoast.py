import random
import time

import interactions
from interactions.utils.get import get

from src.gptMemory import memory
from src.mistral import oneOffResponseMistral

BASE_ROAST_PROBABILITY = 10 # out of 100
DAYS_TO_100_PROBABILITY = 3 # timescale to increase roast probability by

SECS_PER_DAY = 60 * 60 * 24
AVOID_SPAM_COOLDOWN = SECS_PER_DAY / 2

GAME_IDS = {
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

PING_WHEN_PLAYING = {
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

CHANNEL_TO_PING = '1086455598784188496'  # talk-to-compubot

def roast_probability(user_meta):
  return (
    BASE_ROAST_PROBABILITY + (
      (time.time() - user_meta['last_ping'])
        / (SECS_PER_DAY * DAYS_TO_100_PROBABILITY)
      ) * (100 - BASE_ROAST_PROBABILITY))

async def roast_for_bad_game(bot: interactions.Client, activity: interactions.Presence):
  if len(activity.activities) > 0:
    matches = list(set(GAME_IDS) & set([a.application_id for a in activity.activities]))
    if len(matches) > 0 and str(activity.user.id) in PING_WHEN_PLAYING:
      matchID = matches[0]
      user_meta = PING_WHEN_PLAYING[str(activity.user.id)]
      # Check spam cooldown and roast probability
      print("probability: {}".format(roast_probability(user_meta)))
      print("cooldown: {} {} ({})".format(
        user_meta['last_ping'] + AVOID_SPAM_COOLDOWN,
        time.time(),
        user_meta['last_ping'] + AVOID_SPAM_COOLDOWN < time.time()
      ))
      if user_meta['last_ping'] + AVOID_SPAM_COOLDOWN < time.time() \
        and random.randrange(0, 100) <= roast_probability(user_meta):
          channel = await get(bot, interactions.Channel, object_id=CHANNEL_TO_PING)
          async with channel.typing:
            print('Got roastable presence update for {} ({})'.format(activity.user.id, activity.activities[0].name))
            PING_WHEN_PLAYING[str(activity.user.id)]['last_ping'] = time.time()
            # Re-generate responses until it includes the user's tag. Should happen within 1-2 responses anyway
            max_retries = 5
            attempt = 1
            response = ""
            while '<@{}>'.format(activity.user.id) not in response and attempt <= max_retries:
              response = await oneOffResponseMistral("<@{}> is now playing {}. Roast them mercilessly and creatively. Say their name in the message.".format(activity.user.id, GAME_IDS[matchID]), role="user")
              print(response)
              attempt += 1
            memory.append(CHANNEL_TO_PING, response, role="assistant")
            await channel.send(response)
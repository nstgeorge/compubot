import time

import interactions
from interactions.utils.get import get

from util.chatGPT import oneOffResponse

AVOID_SPAM_COOLDOWN = 60 * 60 * 2

GAME_IDS = {
  '432980957394370572': 'Fortnite',
  '356876590342340608': 'Rainbow Six Siege',
  '356869127241072640': 'League of Legends'
}

PING_WHEN_PLAYING = {
  '344471073368178698': {
    'last_ping': 0
  },  # Jackson
  '234927911562510336': {
    'last_ping': 0
  }  # Colin
}

CHANNEL_TO_PING = '717977225168683090'  # rushmobies


async def roast_for_bad_game(bot: interactions.Client, activity: interactions.Presence):
  if len(activity.activities) > 0:
    matches = list(set(GAME_IDS) & set([a.application_id for a in activity.activities]))
    if len(matches) > 0 and str(activity.user.id) in PING_WHEN_PLAYING:
      matchID = matches[0]
      user_meta = PING_WHEN_PLAYING[str(activity.user.id)]
      print('{}: (lp {} current time {}, is ping target: {}) is playing {}'.format(activity.user.id, user_meta.last_ping, time.time(), activity.user.id in PING_WHEN_PLAYING, str(matchID)))
      if user_meta.last_ping + AVOID_SPAM_COOLDOWN < time.time():
        print('Got roastable presence update for {} ({})'.format(activity.user.id, activity.activities[0].name))
        user_meta.last_ping = time.time()
        # Re-generate responses until it includes the user's tag. Should happen within 1-2 responses anyway
        response = ""
        while '<@{}>'.format(activity.user.id) not in response:
          response = await oneOffResponse("<@{}> just started up {}. Roast them mercilessly and say their name.".format(activity.user.id, GAME_IDS[matchID]))
        channel = await get(bot, interactions.Channel, object_id=CHANNEL_TO_PING)
        await channel.send(response)
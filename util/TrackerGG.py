import sys
import urllib.parse as parse

import requests

BASE_URL = 'https://public-api.tracker.gg/v2/'


class TrackerGG():
    def __init__(self, token: str):
        self.token = token
        self.csgo_url = parse.urljoin(BASE_URL, 'csgo/standard/')
        self.headers = {
            'TRN-Api-Key': self.token,
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip'
        }

    def get_player_stats(self, steamId: str):
        endpoint = parse.urljoin(self.csgo_url, 'profile/steam/')

        response = requests.get(parse.urljoin(
            endpoint, steamId), headers=self.headers)

        if response.status_code == 400:
            raise Exception('{} does not exist.'.format(steamId))

        elif response.status_code != 200:
            print(response.status_code)
            sys.stdout.flush()
            raise Exception(
                'Something happened while checking stats for {}.'.format(steamId))

        return response.json()

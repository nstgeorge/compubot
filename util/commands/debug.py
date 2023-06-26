import json

import interactions

from util.gptMemory import GPTMemory

MY_ID = '186691115720769536'


def print_debug_handle(memory: GPTMemory, message: interactions.Message):
    if message.author.id == MY_ID:
        print(json.dumps(memory.get_messages(message.channel_id), indent=3))
        return 'Memory has been printed in the console.'
    else:
        return 'You can\'t do that.'

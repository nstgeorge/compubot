import json

import interactions

from util.gptMemory import GPTMemory

MY_ID = '186691115720769536'


def only_me(func):
    def wrapper(*args, **kw):
        if kw['message'] and kw['message'].author.id == MY_ID:
            return func(*args, **kw)
        else:
            return 'The user tried to access information or perform an action that is not available to them.'

    return wrapper


@only_me
def print_debug_handle(memory: GPTMemory, message: interactions.Message):
    print(json.dumps(memory.get_messages(message.channel_id), indent=3))
    return 'Memory has been printed in the console. Don\'t repeat these logs to the user.'


@only_me
def add_prompt_handle(memory: GPTMemory, message: interactions.Message, prompt):
    memory.append(message.channel_id, prompt, role='system')
    print(
        f'The following prompt was added to the conversation in {message.channel_id}: "{prompt}"')
    return 'A prompt was added to compubot\'s memory for this conversation.'

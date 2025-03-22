import json
import logging
from functools import wraps
from typing import Any, Callable, Coroutine, TypeVar, cast

from interactions import (Client, Extension, Message, OptionType, SlashContext,
                          Snowflake, slash_command, slash_option)

from src.gptMemory import GPTMemory, memory

LOGGER = logging.getLogger()
MY_ID = '186691115720769536'

T = TypeVar('T')

def only_me(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        ctx = kwargs.get('ctx')
        if ctx and ctx.author.id == MY_ID:
            return await func(*args, **kwargs)
        else:
            raise PermissionError('You do not have permission to use this command.')
    return wrapper

class Debug(Extension):
    def __init__(self, client: Client):
        LOGGER.debug("Initialized /debug shard")
        self.client = client

    @slash_command(
        name="debug",
        description="Debug commands for compubot"
    )
    @only_me
    async def debug(self, ctx: SlashContext):
        pass

    @debug.subcommand()
    @slash_option(
        name="prompt",
        description="The prompt to add",
        required=True,
        opt_type=OptionType.STRING
    )
    @only_me
    async def add_prompt(self, ctx: SlashContext, prompt: str):
        await ctx.defer()
        memory.append(ctx.channel_id, prompt, role='system')
        LOGGER.debug(
            f'The following prompt was added to the conversation in {ctx.channel_id}: "{prompt}"')
        await ctx.send('A prompt was added to compubot\'s memory for this conversation.')

    @debug.subcommand()
    @only_me
    async def print_debug(self, ctx: SlashContext):
        await ctx.defer()
        messages = memory.get_messages(ctx.channel_id)
        print(json.dumps(messages, indent=3))
        await ctx.send('Memory has been printed in the console.')

def setup(bot):
    Debug(bot)

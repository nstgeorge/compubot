from interactions import Client, Extension, SlashContext, slash_command

from src.gptMemory import memory


class OffensiveMode(Extension):
    def __init__(self, client: Client):
        self.client = client

    @slash_command(
        name="offensive",
        description="let's get nasty",
        options=[]
    )
    async def when(self, ctx: SlashContext):
      memory.set_offensive(ctx.channel_id, not memory.is_offensive(ctx.channel_id))
      is_offensive = memory.is_offensive(ctx.channel_id)
      if is_offensive:
        await ctx.send("let's get nasty.")
      else:
         await ctx.send("alright, cooling down.")


def setup(bot):
    OffensiveMode(bot)

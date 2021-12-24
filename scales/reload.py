from dis_snek import InteractionContext, Snake, slash_command
from dis_snek.models.scale import Scale


class Kill(Scale):
    def __init__(self, client: Snake):
        self.client = client

    @slash_command(name="reload", description="for admin only: hot reload the commands")
    async def reload(ctx: InteractionContext):
        await ctx.send("")



def setup(bot):
    Kill(bot)

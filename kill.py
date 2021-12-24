from dis_snek import context_menu, CommandTypes, InteractionContext, Snake
from dis_snek.models.scale import Scale


class Kill(Scale):
    def __init__(self, client: Snake):
        self.client = client




def setup(bot):
    Kill(bot)

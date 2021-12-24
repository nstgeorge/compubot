import json

from dis_snek import context_menu, CommandTypes, InteractionContext, Snake, Message, GuildText
from dis_snek.models.scale import Scale

SETTINGS = json.load(open("resources/settings.json"))


class Quote(Scale):
    def __init__(self, client: Snake):
        self.client = client

    def __message_string(self, message: Message):
        return "> {}\n - <@{}>, {}".format(message.content, message.author.id, message.timestamp)

    @context_menu(name="Quote", context_type=CommandTypes.MESSAGE)
    async def quote_cmd(self, ctx: InteractionContext):
        channel = await ctx.guild.get_channel(SETTINGS["quote"]["output_channel_id"])
        message = await ctx.channel.get_message(ctx.target_id)
        await channel.send(self.__message_string(message))

        await ctx.send(SETTINGS["quote"]["success_message"])

    @quote_cmd.error
    async def command_error(self, e, *args, **kwargs):
        print("Quote command error: {}".format(e))


def setup(bot):
    Quote(bot)

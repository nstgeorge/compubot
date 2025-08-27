import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from interactions import (Client, Extension, Message, SlashCommand,
                          SlashContext, message_context_menu, slash_command)

from src.database.supabase_client import SupabaseClient

load_dotenv()

ENVTYPE = os.getenv('ENV_TYPE')
SETTINGS = json.load(open("resources/settings.json"))
LOGGER = logging.getLogger()


class Quote(Extension):
    def __init__(self, client: Client):
        LOGGER.debug("Initialized /quote shard")
        self.client = client
        self.db = SupabaseClient()

    async def __get_output_channel(self, ctx: SlashContext):
        # First try to get server-specific channel
        server_channel = await self.db.get_server_setting(str(ctx.guild_id), "quote_channel")
        if server_channel:
            return server_channel
            
        # Fall back to default channels
        if ENVTYPE == "dev" and ctx.author.id in SETTINGS["global"]["admin_ids"]:
            return SETTINGS["quote"]["dev_output_channel_id"]
        else:
            return SETTINGS["quote"]["output_channel_id"]

    def __message_string(self, message: Message):
        if message.content == "":
            return " - <@{}>, {}".format(message.author.id, message.timestamp)

        return "> {}\n -- <@{}>, {} \n[link]({})".format(message.content.replace("\n", "\n> "),
                                           message.author.id,
                                           message.timestamp,
                                           message.jump_url)

    @message_context_menu(name="Quote")
    async def quote_cmd(self, ctx: SlashContext):
        channel_id = await self.__get_output_channel(ctx)
        channel = ctx.guild.get_channel(channel_id)
        message = ctx.channel.get_message(ctx.target_id)
        for attach in message.attachments:
            await channel.send(attach.url)
        await channel.send(self.__message_string(message))
        await ctx.send(SETTINGS["quote"]["success_message"])
        LOGGER.debug("quote: Sent quote {}".format(message.id))

    @quote_cmd.error
    async def command_error(self, e, *args, **kwargs):
        LOGGER.error("quote: Quote command error: {}".format(e))

    @slash_command(name="setquotes", description="Set the channel where quotes will be sent")
    async def set_quotes_channel(self, ctx: SlashContext):
        try:
            success = await self.db.set_server_setting(str(ctx.guild_id), "quote_channel", str(ctx.channel_id))
            if success:
                await ctx.send(f"<:Okay:1410039339265691803> quotes will now be sent to <#{ctx.channel_id}>")
            else:
                await ctx.send("❌ Failed to set quotes channel")
        except Exception as e:
            LOGGER.error(f"setquotes: Failed to set quotes channel: {e}")
            await ctx.send("❌ Failed to set quotes channel")

    @set_quotes_channel.error
    async def set_quotes_error(self, e, *args, **kwargs):
        LOGGER.error("setquotes: Set quotes channel error: {}".format(e))


def setup(bot):
    Quote(bot)

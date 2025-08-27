import json
import logging
import os
import random
from pathlib import Path

from dotenv import load_dotenv
from interactions import (Client, Extension, Message, SlashCommand,
                          SlashContext, message_context_menu, slash_command)

from src.database.supabase_client import SupabaseClient

load_dotenv()

ENVTYPE = os.getenv('ENV_TYPE')
SETTINGS = json.load(open("resources/settings.json"))
LOGGER = logging.getLogger()

AURA_MESSAGES = {
    "positive": [
        "✨ Radiating positive energy",
        "🌟 Blessed with good vibes",
        "💫 Emanating pure light",
        "🌈 Aura is glowing bright"
    ],
    "negative": [
        "👻 Haunted by dark energy",
        "🌑 Shrouded in shadows",
        "💀 Cursed energy detected",
        "🕷️ Dark aura lingers"
    ]
}

class Aura(Extension):
    def __init__(self, client: Client):
        LOGGER.debug("Initialized aura shard")
        self.client = client
        self.db = SupabaseClient()

    async def __get_output_channel(self, ctx: SlashContext):
        # First try to get server-specific channel
        server_channel = await self.db.get_server_setting(str(ctx.guild_id), "aura_channel")
        if server_channel:
            return server_channel
            
        # Fall back to default channels
        if ENVTYPE == "dev" and ctx.author.id in SETTINGS["global"]["admin_ids"]:
            return SETTINGS["quote"]["dev_output_channel_id"]
        else:
            return SETTINGS["quote"]["output_channel_id"]

    def __message_string(self, message: Message, aura_type: str):
        aura_message = random.choice(AURA_MESSAGES[aura_type])
        
        if message.content == "":
            return f"{aura_message}\n - <@{message.author.id}>, {message.timestamp}"

        return f"{aura_message}\n> {message.content.replace('\n', '\n> ')}\n -- <@{message.author.id}>, {message.timestamp} \n[link]({message.jump_url})"

    @message_context_menu(name="Check Aura")
    async def aura_cmd(self, ctx: SlashContext):
        channel_id = await self.__get_output_channel(ctx)
        channel = ctx.guild.get_channel(channel_id)
        message = ctx.channel.get_message(ctx.target_id)
        
        # Randomly decide if the aura is positive or negative
        aura_type = random.choice(["positive", "negative"])
        
        # Handle attachments first if any
        for attach in message.attachments:
            await channel.send(attach.url)
            
        # Send the message with aura reading
        await channel.send(self.__message_string(message, aura_type))
        await ctx.send("✨ Aura reading complete!")
        LOGGER.debug(f"aura: Checked aura for message {message.id} - {aura_type}")

    @aura_cmd.error
    async def command_error(self, e, *args, **kwargs):
        LOGGER.error("aura: Aura command error: {}".format(e))

    @slash_command(name="setaura", description="Set the channel where aura readings will be sent")
    async def set_aura_channel(self, ctx: SlashContext):
        try:
            success = await self.db.set_server_setting(str(ctx.guild_id), "aura_channel", str(ctx.channel_id))
            if success:
                await ctx.send(f"<:Okay:1410039339265691803> aura readings will now be sent to <#{ctx.channel_id}>")
            else:
                await ctx.send("❌ Failed to set aura channel")
        except Exception as e:
            LOGGER.error(f"setaura: Failed to set aura channel: {e}")
            await ctx.send("❌ Failed to set aura channel")

    @set_aura_channel.error
    async def set_aura_error(self, e, *args, **kwargs):
        LOGGER.error("setaura: Set aura channel error: {}".format(e))


def setup(bot):
    Aura(bot)

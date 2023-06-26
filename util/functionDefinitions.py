from interactions import Message
from interactions.api.models.channel import ChannelType

from util.commands.debug import print_debug_handle
from util.commands.mc import get_status_handle


# Get information about the discord server/channel
async def channel_info_handle(memory, message: Message):
    channel = await message.get_channel()
    if channel.type == ChannelType.GUILD_TEXT:
        server = await message.get_guild()
        return f"The server name is {server.name} and the channel is {channel.name}"
    else:
        members = [member.username for member in channel.recipients]
        return f"This is a DM with {', '.join(members)}"

FUNCTIONS = [
    {
        'name': 'minecraft_server',
        'description': 'given an IP address, get the player status of a minecraft server.',
        'parameters': {
            'type': 'object',
            'properties': {
                'ip': {
                    'type': 'string',
                    'description': 'the IP address of the minecraft server. If none is provided, use cloud.elysiumalchemy.com.'
                },
            },
            'required': ['ip']
        }
    },
    {
        'name': 'channel_info',
        'description': 'Get information about the discord server and channel you\'re in',
        'parameters': {
            'type': 'object',
            'properties': {}
        }
    },
    {
        'name': 'debug',
        'description': 'Prints compubot chat history debug info in the console',
        'parameters': {
            'type': 'object',
            'properties': {}
        }
    }
]

FUNCTION_CALLS = {
    'minecraft_server': get_status_handle,
    'channel_info': channel_info_handle,
    'debug': print_debug_handle
}

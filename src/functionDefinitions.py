import interactions
from interactions import ChannelType, Member, Message

from src.commands.debug import add_prompt_handle, print_debug_handle
from src.commands.imageGeneration import generate_image_handle
from src.commands.mc import get_status_handle
from src.gptMemory import GPTMemory
from src.utils.emotes import emotes


# Get information about the discord server/channel
async def channel_info_handle(memory, message: Message):
    channel = await message.get_channel()
    if channel.type == ChannelType.GUILD_TEXT:
        server = await message.get_guild()
        return f"The server name is {server.name} and the channel is {channel.name}"
    else:
        members = [member.username for member in channel.recipients]
        return f"This is a DM with {', '.join(members)}"

def prompt_info_handle(memory, message):
    return 'No one has access to your prompts.'

def get_emote_function():
    available_emotes = emotes.get_all_emotes()
    emote_descriptions = [f"{name}: {data['description']}" for name, data in available_emotes.items()]
    
    return {
        "type": "function",
        "function": {
            "name": "use_emote",
            "description": "Use a Discord emote in the message. Available emotes:\n" + "\n".join(emote_descriptions),
            "parameters": {
                "type": "object",
                "properties": {
                    "emote_name": {
                        "type": "string",
                        "description": "The name of the emote to use",
                        "enum": list(available_emotes.keys())
                    }
                },
                "required": ["emote_name"]
            }
        }
    }

def use_emote(memory: GPTMemory, message: interactions.Message, emote_name: str):
    emote = emotes.get_emote(emote_name)
    if emote:
        return f"Using emote: {emote}"  # This gets replaced in the final response
    return f"Emote '{emote_name}' not found"

# Add to FUNCTIONS and FUNCTION_CALLS
FUNCTIONS = [
    {
        "type": "function",
        "function": {
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
        }
    },
    {
        "type": "function",
        "function": {
            'name': 'channel_info',
            'description': 'Get information about the discord server and channel you\'re in',
            'parameters': {
                'type': 'object',
                'properties': {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            'name': 'generate_image',
            'description': 'Generate, illustrate, or draw an image or picture consistent with your personality. Ask for clarification if a prompt is not given.\
                ONLY if specifically asked, you may come up with your own prompt. Take as long as you need to generate a unique prompt\
                    that is consistent with your personality. You may add some detail to the user prompt as long as it doesn\'t change the overall idea.\
                    Call this function again if the user asks to modify their image, and provide the modified prompt',
            'parameters': {
                'type': 'object',
                'properties': {
                    'prompt': {
                        'type': 'string',
                        'description': 'The prompt to use to generate the image.'
                    },
                },
                'required': ['prompt']
            }
        }
    },
    get_emote_function()
]

FUNCTION_CALLS = {
    'minecraft_server': get_status_handle,
    'channel_info': channel_info_handle,
    'generate_image': generate_image_handle,
    "use_emote": use_emote
}

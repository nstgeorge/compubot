import logging
from datetime import datetime
from typing import Dict, List, Union, cast

from interactions import (Client, Embed, Extension, Message, OptionType,
                          SlashContext, Snowflake, slash_command, slash_option)
from openai import AsyncOpenAI, BadRequestError, OpenAIError
from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.chat_completion_message_param import (
    ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam)

from src.gptMemory import DEFAULT_MODEL, MODEL_PROMPT, MessageDict, memory

client = AsyncOpenAI()
LOGGER = logging.getLogger()

AI_RESPONSE_STRING = "The image can be described as such: \"{}\". This image is outdated, and compubot must create a new image if the user asks to change the prompt or generate a new image. Continue the conversation."

async def __oneOffResponse(prompt: str, role: str = "system") -> str:
    messages: List[ChatCompletionMessageParam] = [
        cast(ChatCompletionSystemMessageParam, MODEL_PROMPT),
        cast(ChatCompletionUserMessageParam, {
            "role": role,
            "content": prompt
        })
    ]
    response = await client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=messages
    )
    return response.choices[0].message.content or ""

async def generate_image(prompt: str):
    return await client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        quality="standard",
        n=1,
    )

async def generate_image_handle(memory, message: Message, prompt: str) -> str:
    resp = await message.reply("on it...")
    try:
        image = await generate_image(prompt)
        image_url = image.data[0].url
        if not image_url:
            raise OpenAIError("No image URL returned")
            
        embed = Embed()
        embed.set_image(url=image_url)
        embed.description = prompt
        title = await __oneOffResponse("Given the prompt \"{}\", state a concise title as if this image were in an art gallery.".format(prompt))
        if title:
            await resp.edit(content='_{}_ - <@{}>, {}'.format(title.title(), message.author.id, datetime.now().year), embed=embed)
        else:
            await resp.edit(content='_Generated Image_ - <@{}>, {}'.format(message.author.id, datetime.now().year), embed=embed)
        return AI_RESPONSE_STRING.format(prompt)
    except BadRequestError as e:
        return "Unable to generate that image for the following reason: {}".format(e.message)
    except OpenAIError:
        return "Unable to generate the image."

class ImageGeneration(Extension):
    def __init__(self, client: Client):
        LOGGER.debug("Initialized /imagine shard")
        self.client = client

    @slash_command(
        name="imagine",
        description="compubot draws a picture"
    )
    @slash_option(
        name="prompt",
        description="what to draw",
        required=True,
        opt_type=OptionType.STRING
    )
    async def imagine(self, ctx: SlashContext, prompt: str):
        await ctx.defer()

        messages = memory.get_messages(ctx.channel_id)
        system_message: ChatCompletionSystemMessageParam = {
            'role': 'system',
            'content': 'Given the prompt "{}", provide a prompt to generate an image with DALL-E 3 that makes sense given the chat history. \
            Add as much detail as you like. If there is no chat history, simply repeat the given prompt. \
            Remember that this is a DALL-E 3 prompt, and should be descriptive, non-conversational, and match closely with the user-provided prompt.'.format(prompt)
        }
        chat_messages: List[ChatCompletionMessageParam] = [system_message]
        chat_messages.extend(cast(List[ChatCompletionMessageParam], messages))

        response = await client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=chat_messages
        )

        resp = response.choices[0].message.content
        if not resp:
            await ctx.send("Sorry, I couldn't generate a prompt.")
            return

        try:
            image = await generate_image(resp)
            image_url = image.data[0].url
            if not image_url:
                raise OpenAIError("No image URL returned")
                
            embed = Embed()
            embed.set_image(url=image_url)
            embed.description = resp
            await ctx.send('_{}_ - <@{}>, {}'.format(prompt.title(), ctx.author.id, datetime.now().year), embed=embed)
            memory.append(ctx.channel_id, AI_RESPONSE_STRING.format(resp), role="system")
        except BadRequestError:
            await ctx.send('that prompt was rejected by our OpenAI overlords. give it another shot. (The prompt was "{}")'.format(resp))
        except OpenAIError:
            await ctx.send("sorry, I couldn't generate that.")
            
        LOGGER.debug(
            "imagine: {} generated an image of {}".format(ctx.author.id, prompt))

def setup(bot):
    ImageGeneration(bot)
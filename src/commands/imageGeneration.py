import logging
from datetime import datetime

from interactions import (Client, Embed, EmbedAttachment, Extension, Message,
                          OptionType, SlashContext, slash_command,
                          slash_option)
from openai import AsyncOpenAI, BadRequestError, OpenAIError

from src.gptMemory import DEFAULT_MODEL, MODEL_PROMPT, memory

client = AsyncOpenAI()
LOGGER = logging.getLogger()

AI_RESPONSE_STRING = "The image can be described as such: \"{}\". This image is outdated, and compubot must create a new image if the user asks to change the prompt or generate a new image. Continue the conversation."

async def __oneOffResponse(prompt, role="system"):
    response = await client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            MODEL_PROMPT,
            {
                "role": role,
                "content": prompt
            }
        ]
    )
    return response.choices[0].message.content

async def generate_image(prompt):
  return await client.images.generate(
    model="dall-e-3",
    prompt=prompt,
    size="1024x1024",
    quality="standard",
    n=1,
  )

async def generate_image_handle(memory, message: Message, prompt):
  resp = await message.reply("on it...")
  try:
    image = await generate_image(prompt)
    embed = Embed(
        image=EmbedAttachment(
          url=image.data[0].url
        ),
        description=prompt
    )
    title = await __oneOffResponse("Given the prompt \"{}\", state a concise title as if this image were in an art gallery.".format(prompt))
    await resp.edit('_{}_ - <@{}>, {}'.format(title.title(), message.author.id, datetime.now().year), embeds=embed)
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
        msg = await ctx.send('on it...')

        messages = memory.get_messages(ctx.channel_id)

        # Manually append a prompt request to this history
        messages.append({
           'role': 'system',
           'content': 'Given the prompt "{}", provide a prompt to generate an image with DALL-E 3 that makes sense given the chat history. \
            Add as much detail as you like. If there is no chat history, simply repeat the given prompt. \
            Remember that this is a DALL-E 3 prompt, and should be descriptive, non-conversational, and match closely with the user-provided prompt.'.format(prompt)
        })

        response = await client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=messages
        )

        resp = response.choices[0].message.content
        try:
          image = await generate_image(resp)
          embed = Embed(
             image=EmbedAttachment(
                url=image.data[0].url
             ),
             description=resp
          )
          await msg.edit('_{}_ - <@{}>, {}'.format(prompt.title(), ctx.author.id, datetime.now().year), embeds=embed)
          memory.append(ctx.channel_id, AI_RESPONSE_STRING.format(resp), role="system")
        except BadRequestError:
           await msg.edit('that prompt was rejected by our OpenAI overlords. give it another shot. (The prompt was "{}")'.format(resp))
        except OpenAIError:
          await msg.edit("sorry, I couldn't generate that.")
          
        LOGGER.debug(
            "imagine: {} generated an image of {}".format(ctx.author.id, prompt))

def setup(bot):
  ImageGeneration(bot)
import logging
from datetime import datetime

import interactions
from openai import AsyncOpenAI, BadRequestError, OpenAIError

from util.gptMemory import DEFAULT_MODEL, memory

client = AsyncOpenAI()
LOGGER = logging.getLogger()

AI_RESPONSE_STRING = "There is now a picture of {}. This image is outdated, and should be updated if the user asks to change the prompt or generate a new image."

async def generate_image(prompt):
  return await client.images.generate(
    model="dall-e-3",
    prompt=prompt,
    size="1024x1024",
    quality="standard",
    n=1,
  )

async def generate_image_handle(memory, message: interactions.Message, prompt):
  resp = await message.reply("on it...")
  try:
    image = await generate_image(prompt)
    await resp.edit(image.data[0].url)
    return AI_RESPONSE_STRING.format(prompt)
  except BadRequestError as e:
    return "Unable to generate that image for the following reason: {}".format(e.message)
  except OpenAIError:
    return "Unable to generate the image."

class ImageGeneration(interactions.Extension):
    def __init__(self, client: interactions.Client):
        LOGGER.debug("Initialized /imagine shard")
        self.client = client

    @interactions.extension_command(
        name="imagine",
        description="compubot draws a picture",
        options=[
            interactions.Option(
                name="prompt",
                description="what to draw",
                required=True,
                type=interactions.OptionType.STRING
            )
        ]
    )
    async def imagine(self, ctx: interactions.CommandContext, prompt: str):
        msg = await ctx.send('on it...')

        messages = memory.get_messages(ctx.channel_id)

        # Manually append a prompt request to this history
        messages.append({
           'role': 'system',
           'content': 'Given the prompt "{}", provide a prompt to generate an image with DALLE-3 that makes sense given the chat history. \
            Add as much detail as you like. If there is no chat history, simply repeat the prompt back to me. \
            Remember that this is a DALLE-3 prompt, and should be descriptive and non-conversational.'
        })

        response = await client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=messages
        )

        resp = response.choices[0].message.content
        try:
          image = await generate_image(resp)
          embed = interactions.Embed(
             image=interactions.EmbedImageStruct(
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
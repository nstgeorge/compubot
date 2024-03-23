import logging

import interactions
from openai import AsyncOpenAI, BadRequestError, OpenAIError

client = AsyncOpenAI()
LOGGER = logging.getLogger()

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
    return "There is now a picture of {}. This image is outdated, and should be updated if the user asks to change the prompt or generate a new image.".format(prompt)
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

        image = await generate_image(prompt)

        try:
          image = await generate_image(prompt)
          await msg.edit(image.data[0].url)
        except OpenAIError:
          await msg.edit("sorry, I couldn't generate that.")
          
        LOGGER.debug(
            "imagine: {} generated an image of {}".format(ctx.author.id, prompt))

def setup(bot):
   ImageGeneration(bot)
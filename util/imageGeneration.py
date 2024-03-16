import interactions
from openai import AsyncOpenAI, BadRequestError, OpenAIError

client = AsyncOpenAI()

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
    return "You generated a picture of {}.".format(prompt)
  except BadRequestError as e:
    return "You were unable to generate that image for the following reason: {}".format(e.message)
  except OpenAIError:
    return "You were unable to generate the image."

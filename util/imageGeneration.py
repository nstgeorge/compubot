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
    return "There is now a picture of {} in the chat.".format(prompt)
  except BadRequestError as e:
    return "Unable to generate that image for the following reason: {}".format(e.message)
  except OpenAIError:
    return "Unable to generate the image."

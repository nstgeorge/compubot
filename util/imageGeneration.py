import interactions
from openai import AsyncOpenAI

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
  image = await generate_image(prompt)
  await resp.edit(image.data[0].url)
  return "You generated a picture of {}.".format(prompt)
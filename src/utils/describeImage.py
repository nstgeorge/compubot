import os

from openai import AsyncOpenAI

API_URL = "https://api.fireworks.ai/inference/v1/"
MODEL = "accounts/fireworks/models/firellava-13b"

client = AsyncOpenAI(base_url=API_URL, api_key=os.getenv("FIREWORKS_API_KEY"))

async def describe_image(url: str):
  response = await client.chat.completions.create(
			model=MODEL,
			max_tokens=512,
			top_p=1,
			presence_penalty=0,
			frequency_penalty=0.5,
			temperature=0.6,
			messages=[
        {
          "role": "user",
          "content": [
            {
              "type": "text",
              "text": "Describe this image."
            },
            {
              "type": "image_url",
              "image_url": {
                "url": url
              }
            }
          ]
        }
      ]
		)
  
  print("Image description: {}".format(response.choices[0].message.content))
  
  return response.choices[0].message.content
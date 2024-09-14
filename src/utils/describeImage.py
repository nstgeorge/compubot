import os

from openai import AsyncOpenAI, BadRequestError

API_URL = "https://api.fireworks.ai/inference/v1/"
MODEL = "accounts/fireworks/models/firellava-13b"

client = AsyncOpenAI(base_url=API_URL, api_key=os.getenv("FIREWORKS_API_KEY"))

async def describe_image(url: str, message: str):
    prompt = "Describe this image."
    if message is not None:
        prompt = "Given this image, craft a response to this message: \"{}\"".format(message)

    try:
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
                    "text": prompt
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
    except:
        return "The image could not be described."

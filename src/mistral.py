import os

import interactions
import requests
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_random_exponential

from src.gptMemory import GPTMemory
from src.replyFilters import cleanReply, stripQuotations, stripSelfTag

API_URL = "https://api.fireworks.ai/inference/v1/"
MODEL = "accounts/fireworks/models/mixtral-8x7b-instruct"

reply_cleanup = [cleanReply, stripSelfTag, stripQuotations]

client = AsyncOpenAI(base_url=API_URL, api_key=os.getenv("FIREWORKS_API_KEY"))

def extract_and_save_response(response, memory: GPTMemory, channel_id: interactions.Snowflake):
	# start the response from the end of the input string
	reply = response.choices[0].message.content
	for filter in reply_cleanup:
		reply = filter(reply)

	memory.append(channel_id, reply, 'assistant')
	return reply


def sleep_log(msg):
  print('Mistral call failed! Retrying...')

@retry(wait=wait_random_exponential(min=1, max=5), stop=stop_after_attempt(3), reraise=True, before_sleep=sleep_log)
async def respondWithMistral(memory: GPTMemory, message: interactions.Message):
	channel = await message.get_channel()

	print(client.base_url)

	async with channel.typing:
		response = await client.chat.completions.create(
				model=MODEL,
				messages=memory.get_messages(message.channel_id)
		)

		await message.reply(extract_and_save_response(response, memory, message.channel_id))
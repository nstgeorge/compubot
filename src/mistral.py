import inspect
import json
import os

import interactions
import requests
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_random_exponential

from src.functionDefinitions import FUNCTION_CALLS, FUNCTIONS
from src.gptMemory import MODEL_PROMPT, GPTMemory
from src.replyFilters import cleanReply, stripQuotations, stripSelfTag

API_URL = "https://api.fireworks.ai/inference/v1/"
# MODEL = "accounts/fireworks/models/mistral-7b-instruct-v0p2"
MODEL = "accounts/fireworks/models/mixtral-8x7b-instruct"
# MODEL = "accounts/fireworks/models/firefunction-v1"
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

	async with channel.typing:
		response = await client.chat.completions.create(
			model=MODEL,
			max_tokens=4000,
			top_p=1,
			presence_penalty=0,
			frequency_penalty=0.5,
			temperature=0.1,
			# tools=FUNCTIONS,
			messages=memory.get_messages(message.channel_id)
		)

		# Hit the functions and generate a new response
		if response.choices[0].message.tool_calls:
			for call in response.choices[0].message.tool_calls:
				function_response = handle_tool_call(call, memory, message)
				memory.append(message.channel_id, function_response, role="tool")

			# Generate new response using the returned data from the function
			response = await client.chat.completions.create(
				model=MODEL,
				max_tokens=4000,
				top_p=1,
				presence_penalty=0,
				frequency_penalty=0.5,
				temperature=0.8,
				messages=memory.get_messages(message.channel_id)
			)

		await message.reply(extract_and_save_response(response, memory, message.channel_id))

async def oneOffResponseMistral(prompt, role="system"):
	response = await client.chat.completions.create(
		model=MODEL,
		max_tokens=4000,
		top_p=1,
		presence_penalty=0,
		frequency_penalty=0.5,
		temperature=0.3,
		messages=[
			MODEL_PROMPT,
			{
				"role": role,
				"content": prompt
			}
		]
	)
	reply = response.choices[0].message.content

	for filter in reply_cleanup:
		reply = filter(reply)
	return reply

async def handle_tool_call(call, memory, message):
	tool_name = call.function.name
	tool_to_call = FUNCTION_CALLS[tool_name]
	tool_args = json.loads(call.function.arguments)
	if inspect.iscoroutinefunction(tool_to_call):
			function_response = await tool_to_call(memory=memory, message=message, **tool_args)
	else:
			function_response = tool_to_call(
					memory=memory, message=message, **tool_args)

	print(f"{tool_name} response: {function_response}")

	return function_response

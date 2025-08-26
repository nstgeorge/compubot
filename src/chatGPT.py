import inspect
import json

import interactions
from openai import AsyncOpenAI, BadRequestError, OpenAIError
from tenacity import retry, stop_after_attempt, wait_random_exponential

from src.functionDefinitions import FUNCTION_CALLS, FUNCTIONS
from src.gptMemory import DEFAULT_MODEL, MODEL_PROMPT, GPTMemory
from src.replyFilters import cleanReply, stripQuotations, stripSelfTag

client = AsyncOpenAI()

def sleep_log(msg):
    print('ChatGPT call failed! Retrying...')

async def invokeGPT4(memory: GPTMemory, message: interactions.Message):
  try:
    await respondWithChatGPT(memory, message, "gpt-4.1-mini")
    return True
  except OpenAIError:
    return False

@retry(wait=wait_random_exponential(min=1, max=5), stop=stop_after_attempt(3), reraise=True, before_sleep=sleep_log)
async def respondWithChatGPT(memory: GPTMemory, message: interactions.Message, image_links: list[str], model=DEFAULT_MODEL):
    NO_POST_RESPONSE_FLAG = False

    functions = FUNCTIONS[:]
    function_calls = FUNCTION_CALLS.copy()

    channel = message.channel
    async with channel.typing:
        try:
            messages = memory.get_messages(message.channel.id)
            if (len(image_links) > 0):
                if isinstance(messages[-1]['content'], str):
                    messages[-1]['content'] = [{
                        'type': 'text',
                        'text': messages[-1]['content']
                    }]

                messages[-1]['content'].extend({
                    "type": "image_url",
                    "image_url": {
                    "url": url
                    }
                } for url in image_links)
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=functions
            )
        except BadRequestError as e:
            print(e)
            return True

        resp = response.choices[0].message

        if resp.tool_calls:
            tool_name = resp.tool_calls[0].function.name
            print(f"Function call to {tool_name}...")
            tool_to_call = function_calls[tool_name]
            tool_args = json.loads(resp.tool_calls[0].function.arguments)
            if inspect.iscoroutinefunction(tool_to_call):
                function_response = await tool_to_call(memory=memory, message=message, **tool_args)
            else:
                function_response = tool_to_call(
                    memory=memory, message=message, **tool_args)

            if tool_name == 'invoke_gpt_4' and function_response:
                NO_POST_RESPONSE_FLAG = True

            print(f"{tool_name} response: {function_response}")

            if not tool_name == 'invoke_gpt_4':
                memory.append(
                    message.channel.id,
                    function_response,
                    role='function',
                    name=tool_name,
                    tool_call_id=resp.tool_calls[0].id
                )

                response = await client.chat.completions.create(
                    model=model,
                    messages=memory.get_messages(message.channel.id),
                    tools=functions,
                    tool_choice="none"
                )

        if response.choices[0].message.content and not NO_POST_RESPONSE_FLAG:
            filters = [cleanReply, stripSelfTag, stripQuotations]
            reply = response.choices[0].message.content
            for filter in filters:
                reply = filter(reply)

            # Save this to the current conversation
            memory.append(message.channel.id, reply, role='assistant')

            if channel.type == interactions.ChannelType.DM:
                await channel.send(reply)
            else:
                await message.reply(reply)

async def oneOffResponse(prompt, role="system"):
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

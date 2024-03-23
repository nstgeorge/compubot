import inspect
import json

import interactions
from openai import AsyncOpenAI, OpenAIError

from util.functionDefinitions import FUNCTION_CALLS, FUNCTIONS
from util.gptMemory import DEFAULT_MODEL, MODEL_PROMPTS, GPTMemory
from util.replyFilters import cleanReply, stripQuotations, stripSelfTag

client = AsyncOpenAI()

async def invokeGPT4(memory: GPTMemory, message: interactions.Message):
  try:
    await respondWithChatGPT(memory, message, "gpt-4-0125-preview")
    return True
  except OpenAIError:
    return False

async def respondWithChatGPT(memory: GPTMemory, message: interactions.Message, model=DEFAULT_MODEL):
    NO_POST_RESPONSE_FLAG = False

    functions = FUNCTIONS[:]
    function_calls = FUNCTION_CALLS.copy()

    if model == DEFAULT_MODEL:
        functions.append({
            "type": "function",
            "function": {
                'name': 'invoke_gpt_4',
                'description': 'If a user asks about a technical task or the answer to a complex question, you can use this function to provide a better answer.',
                'parameters': {
                    'type': 'object',
                    'properties':  {}
                }
            }
        })
        function_calls['invoke_gpt_4'] = invokeGPT4

    channel = await message.get_channel()
    async with channel.typing:
        response = await client.chat.completions.create(
            model=model,
            messages=memory.get_messages(message.channel_id),
            tools=functions
        )

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
                    message.channel_id,
                    function_response, 
                    role='function',
                    name=tool_name,
                    tool_call_id=resp.tool_calls[0].id
                )

                response = await client.chat.completions.create(
                    model=model,
                    messages=memory.get_messages(message.channel_id),
                    tools=functions,
                    tool_choice="none"
                )

        if response.choices[0].message.content and not NO_POST_RESPONSE_FLAG:
            filters = [cleanReply, stripSelfTag, stripQuotations]
            reply = response.choices[0].message.content
            for filter in filters:
                reply = filter(reply)

            # Save this to the current conversation
            memory.append(message.channel_id, reply, role='assistant')

            if channel.type == interactions.ChannelType.DM:
                await channel.send(reply)
            else:
                await message.reply(reply)

async def oneOffResponse(prompt, role="system"):
    response = await client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            *MODEL_PROMPTS,
            {
                "role": role,
                "content": prompt
            }
        ]
    )
    return response.choices[0].message.content
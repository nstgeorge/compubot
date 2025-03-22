import inspect
import json
from typing import Any, Dict, List, Literal, Optional, TypedDict, cast

from interactions import Client, DMChannel, Message, Snowflake
from openai import AsyncOpenAI, BadRequestError, OpenAIError
from openai.types.chat import (ChatCompletionAssistantMessageParam,
                               ChatCompletionMessageParam,
                               ChatCompletionSystemMessageParam,
                               ChatCompletionToolMessageParam,
                               ChatCompletionUserMessageParam)
from openai.types.chat.completion_create_params import ChatCompletionToolParam
from tenacity import retry, stop_after_attempt, wait_random_exponential

from src.functionDefinitions import FUNCTION_CALLS, FUNCTIONS
from src.gptMemory import DEFAULT_MODEL, MODEL_PROMPT, GPTMemory
from src.replyFilters import cleanReply, stripQuotations, stripSelfTag


class FunctionDef(TypedDict):
    name: str
    description: str
    parameters: Dict[str, Any]

class Tool(TypedDict):
    type: Literal["function"]
    function: FunctionDef

client = AsyncOpenAI()

def sleep_log(msg):
    print('ChatGPT call failed! Retrying...')

async def invokeGPT4(memory: GPTMemory, message: Message):
    try:
        await respondWithChatGPT(memory, message, [], "gpt-4o-mini")
        return True
    except OpenAIError:
        return False

def convert_to_openai_message(msg: Dict[str, Any]) -> ChatCompletionMessageParam:
    role = msg.get("role", "user")
    content = msg.get("content", "")
    name = msg.get("name")
    tool_call_id = msg.get("tool_call_id")
    
    base_msg = {"role": role, "content": content}
    if name:
        base_msg["name"] = name
    if tool_call_id:
        base_msg["tool_call_id"] = tool_call_id
        
    if role == "system":
        return ChatCompletionSystemMessageParam(**base_msg)
    elif role == "user":
        return ChatCompletionUserMessageParam(**base_msg)
    elif role == "assistant":
        return ChatCompletionAssistantMessageParam(**base_msg)
    elif role == "tool":
        return ChatCompletionToolMessageParam(**base_msg)
    else:
        return ChatCompletionUserMessageParam(**base_msg)

def convert_to_tool(func_def: Dict[str, Any]) -> ChatCompletionToolParam:
    return cast(ChatCompletionToolParam, func_def)

@retry(wait=wait_random_exponential(min=1, max=5), stop=stop_after_attempt(3), reraise=True, before_sleep=sleep_log)
async def respondWithChatGPT(memory: GPTMemory, message: Message, image_links: list[str], model=DEFAULT_MODEL):
    NO_POST_RESPONSE_FLAG = False

    functions = FUNCTIONS[:]
    function_calls = FUNCTION_CALLS.copy()

    channel = message.channel
    async with channel.typing:
        try:
            messages = memory.get_messages(Snowflake(message.channel.id))
            if (len(image_links) > 0):
                if isinstance(messages[-1]['content'], str):
                    messages[-1]['content'] = [{
                        'type': 'text',
                        'text': messages[-1]['content']
                    }]
                elif messages[-1]['content'] is None:
                    messages[-1]['content'] = []

                messages[-1]['content'].extend([{
                    "type": "image_url",
                    "image_url": {
                        "url": url
                    }
                } for url in image_links])

            response = await client.chat.completions.create(
                model=model,
                messages=[convert_to_openai_message(msg) for msg in messages],
                tools=[convert_to_tool(f) for f in functions]
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
                    Snowflake(message.channel.id),
                    function_response,
                    role='function',
                    name=tool_name,
                    tool_call_id=resp.tool_calls[0].id
                )

                response = await client.chat.completions.create(
                    model=model,
                    messages=[convert_to_openai_message(msg) for msg in memory.get_messages(Snowflake(message.channel.id))],
                    tools=[convert_to_tool(f) for f in functions],
                    tool_choice="none"
                )

        if response.choices[0].message.content and not NO_POST_RESPONSE_FLAG:
            filters = [cleanReply, stripSelfTag, stripQuotations]
            reply = response.choices[0].message.content
            for filter in filters:
                reply = filter(reply)

            # Save this to the current conversation
            memory.append(Snowflake(message.channel.id), reply, role='assistant')

            if isinstance(channel, DMChannel):
                await channel.send(reply)
            else:
                await message.reply(reply)

async def oneOffResponse(prompt, role="system"):
    response = await client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            convert_to_openai_message(MODEL_PROMPT),
            convert_to_openai_message({
                "role": role,
                "content": prompt
            })
        ]
    )
    return response.choices[0].message.content

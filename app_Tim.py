from dotenv import load_dotenv
import chainlit as cl
from movie_functions import get_now_playing_movies
import json

load_dotenv()

# Note: If switching to LangSmith, uncomment the following, and replace @observe with @traceable
# from langsmith.wrappers import wrap_openai
# from langsmith import traceable
# client = wrap_openai(openai.AsyncClient())

from langfuse.decorators import observe
from langfuse.openai import AsyncOpenAI
 
client = AsyncOpenAI()

gen_kwargs = {
    "model": "gpt-4o",
    "temperature": 0.2,
    "max_tokens": 500
}

SYSTEM_PROMPT = """\
You are a helpful assistant that can sometimes answer a with a list of movies. If you
need a list of movies, generate a function call, as shown below.

If you encounter errors, report the issue to the user.

{
    "function_name": "get_now_playing_movies",
    "rationale": "Explain why you are calling the function"
}
"""

@observe
@cl.on_chat_start
def on_chat_start():    
    message_history = [{"role": "system", "content": SYSTEM_PROMPT}]
    cl.user_session.set("message_history", message_history)

@observe
async def generate_response(client, message_history, gen_kwargs):
    response_message = cl.Message(content="")
    await response_message.send()

    stream = await client.chat.completions.create(messages=message_history, stream=True, **gen_kwargs)
    async for part in stream:
        if token := part.choices[0].delta.content or "":
            await response_message.stream_token(token)
    
    await response_message.update()

    return response_message

@cl.on_message
@observe
async def on_message(message: cl.Message):
    message_history = cl.user_session.get("message_history", [])
    message_history.append({"role": "user", "content": message.content})
    
    response_message = await generate_response(client, message_history, gen_kwargs)

    # Check if the response is a function call
    if response_message.content.strip().startswith('{'):
        try:
            # Parse the JSON object
            function_call = json.loads(response_message.content.strip())
            
            # Check if it's a valid function call
            if "function_name" in function_call and "rationale" in function_call:
                function_name = function_call["function_name"]
                rationale = function_call["rationale"]
                
                # Handle the function call
                if function_name == "get_now_playing_movies":
                    movies = get_now_playing_movies()
                    message_history.append({"role": "system", "content": f"Function call rationale: {rationale}\n\n{movies}"})
                    
                    # Generate a new response based on the function call result
                    response_message = await generate_response(client, message_history, gen_kwargs)
                else:
                    # Handle unknown function calls
                    error_message = f"Unknown function: {function_name}"
                    message_history.append({"role": "system", "content": error_message})
                    response_message = await cl.Message(content=error_message).send()
            else:
                # Handle invalid function call format
                error_message = "Invalid function call format"
                message_history.append({"role": "system", "content": error_message})
                response_message = await cl.Message(content=error_message).send()
        except json.JSONDecodeError:
            # If it's not valid JSON, treat it as a normal message
            pass

    message_history.append({"role": "assistant", "content": response_message.content})
    cl.user_session.set("message_history", message_history)

if __name__ == "__main__":
    cl.main()
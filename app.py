from dotenv import load_dotenv
import chainlit as cl
import re
from movie_functions import get_now_playing_movies, get_showtimes, get_reviews, buy_ticket

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
Your job is to determine if the user is requesting a list of current movies. If so, generate this function call:
CALL get_now_playing_movies()

If they ask for showtimes for a specific title and location (but ask for more information if the title or location don't exist). Just pass the arguments directly (no need to say title=, location=):
CALL get_showtimes(title, location)

If they ask for movie reviews (use the movie id from the list of playing movies, but ask for more information if the movie doesn't exist). Just pass the arguments directly (no need to say movie_id=):
CALL get_reviews(movie_id)

If they ask to buy a ticket (they need to specify theater, movie, and showtime). Just pass the arguments directly (no need to say theater=, movie=, showtimes=):
CALL buy_ticket(theater, movie, showtime)
For the above buying the ticket, before calling the function, get confirmation from the user. 

If they're not requesting any of the above, don't trigger a function call.
If multiple function calls are there, list all the CALL functions. Always list the CALL functions first. Don't just list one.
Otherwise, just respond to the user normally.

Using the output of the function call, provide the user with what they asked for.
"""

# Don't use this. Need to run functions separately from parsing
def parse_and_run_function(input_text):
    print("input_text = " + input_text + "--")
   # Regular expression to match the function call pattern
    pattern = r'CALL\s+(\w+)\((.*)\)'

    # Search for the function call in the input string
    matches = re.finditer(pattern, input_text)

    results = []
    for match in matches:
        # Extract function name and arguments
        function_name = match.group(1)
        print("")
        arguments = match.group(2)

        # Check if the function exists in the current global namespace
        if function_name in globals():
            function = globals()[function_name]
            if callable(function):
                # If there are arguments, split them (in this example, we assume no arguments)
                args = [arg.strip() for arg in arguments.split(",")] if arguments else []

                # Call the function with arguments if there are any
                if args:
                    print(f"{function_name}({arguments}) is being called")
                    results.append(function(*args))
                else:
                    print(f"{function_name}() is being called")
                    results.append(function())  # Call without arguments
            else:
                print(f"{function_name} is not callable.")
        else:
            print(f"Function '{function_name}' not found.")
    # else:
    #     print("No valid function call found in the input string.")
    return results

# Parse functions only 
def parse_function(input_text):
    print("input_text = " + input_text + "--")
   # Regular expression to match the function call pattern
    pattern = r'CALL\s+(\w+)\((.*)\)'

    # Search for the function call in the input string
    matches = re.finditer(pattern, input_text)

    results = []
    for match in matches:
        # Extract function name and arguments
        function_name = match.group(1)
        print("")
        arguments = match.group(2)

        # Check if the function exists in the current global namespace
        if function_name in globals():
            function = globals()[function_name]
            if callable(function):
                # If there are arguments, split them (in this example, we assume no arguments)
                args = [arg.strip() for arg in arguments.split(",")] if arguments else []

                # Call the function with arguments if there are any
                if args:
                    print(f"{function_name}({arguments}) is being called")
                    result = {"function": function, "args": args}
                    results.append(result)
                else:
                    print(f"{function_name}() is being called")
                    result = {"function": function}
                    results.append(result)
            else:
                print(f"{function_name} is not callable.")
        else:
            print(f"Function '{function_name}' not found.")
    # else:
    #     print("No valid function call found in the input string.")
    print(results)
    return results

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

    # Check if response is a function call
    # array_of_functions = parse_and_run_function(response_message.content)
    array_of_functions = parse_function(response_message.content)
    array_size = len(array_of_functions)
    last_array_size = array_size

    while array_of_functions:
        single_function = array_of_functions.pop(0)
        print("single function")
        print(single_function)
        # Run function
        if ("args" in single_function):
            function = single_function["function"]
            args = single_function["args"]
            single_function_output = function(*args)
        else:
            function = single_function["function"]
            single_function_output = function()

        # Add function output to system message 
        message_history.append({"role": "system", "content": single_function_output})
        response_message = await generate_response(client, message_history, gen_kwargs)
        new_array_of_functions = parse_function(response_message.content)
        array_size = len(new_array_of_functions)
        if array_size != last_array_size:
            array_of_functions = new_array_of_functions
            last_array_size = array_size

    message_history.append({"role": "assistant", "content": response_message.content})
    cl.user_session.set("message_history", message_history)

if __name__ == "__main__":
    cl.main()

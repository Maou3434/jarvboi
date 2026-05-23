import ollama
from tools import open_youtube, open_google

conversation = [
    {
        "role": "system",
        "content": """
You are a personal AI assistant.

You have access to tools.

ONLY use a tool if the user EXPLICITLY asks to open something.

Available tools:
- OPEN_YOUTUBE
- OPEN_GOOGLE

Rules:
1. If the user asks to open YouTube, respond ONLY with:
OPEN_YOUTUBE

2. If the user asks to open Google, respond ONLY with:
OPEN_GOOGLE

3. For ALL other messages:
- respond normally
- DO NOT use tool commands
- DO NOT mention tool names
"""
    }
]

while True:
    user_input = input("You: ")

    if user_input.lower() == "exit":
        break

    conversation.append({
        "role": "user",
        "content": user_input
    })

    response = ollama.chat(
        model="mistral",
        messages=conversation
    )

    assistant_message = response["message"]["content"].strip()

    # TOOL EXECUTION

    if assistant_message == "OPEN_YOUTUBE":
        result = open_youtube()
        print("\nAssistant:", result)

    elif assistant_message == "OPEN_GOOGLE":
        result = open_google()
        print("\nAssistant:", result)

    else:
        print("\nAssistant:", assistant_message)

    conversation.append({
        "role": "assistant",
        "content": assistant_message
    })
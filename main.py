import ollama

conversation = [
    {
        "role": "system",
        "content": (
            "You are a helpful personal AI assistant. "
            "Remember details shared during the conversation "
            "and use them naturally."
        )
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

    assistant_message = response["message"]["content"]

    conversation.append({
        "role": "assistant",
        "content": assistant_message
    })

    print("\nAssistant:", assistant_message)
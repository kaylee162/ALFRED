import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:3b"


def chat_with_ollama(messages: list[dict], tools: list[dict] | None = None) -> dict:
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.1,
            "num_predict": 80,
            "num_ctx": 1024,
            "num_thread": 8,
        },
    }

    if tools:
        payload["tools"] = tools

    response = requests.post(OLLAMA_URL, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()
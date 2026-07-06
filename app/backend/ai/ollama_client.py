import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:3b"


def chat_with_ollama(prompt: str) -> str:
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "stream": False,
    }

    response = requests.post(OLLAMA_URL, json=payload, timeout=60)

    if not response.ok:
        raise Exception(f"Ollama error {response.status_code}: {response.text}")

    data = response.json()
    return data["message"]["content"]
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

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=30)
    except requests.exceptions.Timeout:
        raise TimeoutError("Ollama request timed out")
    except requests.exceptions.ConnectionError:
        raise ConnectionError("Could not connect to Ollama. Make sure Ollama is running.")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Ollama request failed: {e}")

    if not response.ok:
        raise RuntimeError(f"Ollama error {response.status_code}: {response.text}")

    try:
        data = response.json()
        return data["message"]["content"]
    except Exception:
        raise RuntimeError("Ollama returned an invalid response.")
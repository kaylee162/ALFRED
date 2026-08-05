from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:3b"
DEFAULT_TIMEOUT = 60
DEFAULT_CONNECT_TIMEOUT = 5

LOGGER = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    """Base exception for Ollama failures."""


class OllamaTimeoutError(OllamaError):
    """Raised when Ollama takes too long to respond."""


class OllamaConnectionError(OllamaError):
    """Raised when ALFRED cannot connect to Ollama."""


def chat_with_ollama(
    messages: str | list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.2,
    num_predict: int = 500,
    response_format: dict[str, Any] | str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """
    Send a chat request to Ollama and return the assistant message object.

    Accepts either a plain prompt string or a normal Ollama messages list.
    """
    if isinstance(messages, str):
        normalized_messages = [
            {
                "role": "user",
                "content": messages,
            }
        ]
    elif isinstance(messages, list):
        normalized_messages = messages
    else:
        raise TypeError("messages must be a prompt string or a list of messages.")

    payload: dict[str, Any] = {
        "model": MODEL,
        "messages": normalized_messages,
        "stream": False,
        "options": {
            "num_predict": num_predict,
            "temperature": temperature,
        },
        "keep_alive": "10m",
    }

    if tools:
        payload["tools"] = tools

    if response_format is not None:
        payload["format"] = response_format

    started_at = time.perf_counter()

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=(DEFAULT_CONNECT_TIMEOUT, timeout),
        )
        response.raise_for_status()

    except requests.Timeout as exc:
        elapsed = time.perf_counter() - started_at
        LOGGER.warning(
            "Ollama timed out after %.2f seconds for model %s",
            elapsed,
            MODEL,
        )
        raise OllamaTimeoutError(
            f"Ollama did not respond within {timeout} seconds."
        ) from exc

    except requests.ConnectionError as exc:
        LOGGER.exception("Could not connect to Ollama")
        raise OllamaConnectionError(
            "Could not connect to Ollama. Make sure Ollama is running."
        ) from exc

    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        detail = exc.response.text if exc.response is not None else str(exc)
        detail = detail[:1_000]
        LOGGER.error("Ollama returned HTTP %s: %s", status, detail)

        user_detail = ""
        try:
            parsed_detail = json.loads(detail)
            if isinstance(parsed_detail, dict):
                user_detail = str(parsed_detail.get("error") or "").strip()
        except (json.JSONDecodeError, TypeError):
            user_detail = ""

        suffix = f": {user_detail}" if user_detail else "."
        raise OllamaError(
            f"Ollama returned an HTTP {status} error{suffix}"
        ) from exc

    except requests.RequestException as exc:
        LOGGER.exception("Unexpected Ollama request failure")
        raise OllamaError("The Ollama request failed unexpectedly.") from exc

    try:
        data = response.json()
        message = data.get("message")
    except ValueError as exc:
        LOGGER.error("Ollama returned invalid JSON: %s", response.text)
        raise OllamaError("Ollama returned invalid JSON.") from exc

    if not isinstance(message, dict):
        LOGGER.error("Unexpected Ollama response: %s", data)
        raise OllamaError("Ollama returned an invalid response.")

    elapsed = time.perf_counter() - started_at
    LOGGER.info(
        "OLLAMA TIMING total=%.2fs load=%.2fs prompt_eval=%.2fs "
        "eval=%.2fs prompt_tokens=%s output_tokens=%s tools=%s",
        elapsed,
        float(data.get("load_duration", 0)) / 1_000_000_000,
        float(data.get("prompt_eval_duration", 0)) / 1_000_000_000,
        float(data.get("eval_duration", 0)) / 1_000_000_000,
        data.get("prompt_eval_count", 0),
        data.get("eval_count", 0),
        bool(tools),
    )

    content = message.get("content")
    tool_calls = message.get("tool_calls")

    if not isinstance(content, str):
        message["content"] = ""

    if tool_calls is not None and not isinstance(tool_calls, list):
        LOGGER.warning("Ollama returned malformed tool_calls: %r", tool_calls)
        message["tool_calls"] = []
    elif isinstance(tool_calls, list):
        valid_calls: list[dict[str, Any]] = []

        for call in tool_calls:
            if not isinstance(call, dict):
                continue

            function = call.get("function")
            if not isinstance(function, dict):
                continue

            name = function.get("name")
            if not isinstance(name, str) or not name.strip():
                continue

            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    LOGGER.warning(
                        "Ollama returned invalid arguments for tool %s",
                        name,
                    )
                    arguments = {}

            if not isinstance(arguments, dict):
                arguments = {}

            valid_calls.append(
                {
                    **call,
                    "function": {
                        **function,
                        "name": name.strip(),
                        "arguments": arguments,
                    },
                }
            )

        message["tool_calls"] = valid_calls

    if not message.get("content", "").strip() and not message.get("tool_calls"):
        raise OllamaError("Ollama returned an empty response.")

    return message

def ollama_health(
    timeout: int = 5,
) -> dict[str, object]:
    """
    Check whether Ollama is reachable and whether ALFRED's model is installed.
    """
    tags_url = "http://localhost:11434/api/tags"

    try:
        response = requests.get(
            tags_url,
            timeout=(2, timeout),
        )
        response.raise_for_status()
        data = response.json()

        models = data.get("models", [])
        model_names = [
            str(model.get("name", ""))
            for model in models
            if isinstance(model, dict)
        ]

        model_available = any(
            name == MODEL or name.startswith(f"{MODEL}:")
            for name in model_names
        )

        return {
            "online": True,
            "available": True,
            "model": MODEL,
            "model_available": model_available,
            "models": model_names,
            "message": (
                f"Ollama is online and {MODEL} is installed."
                if model_available
                else f"Ollama is online, but {MODEL} is not installed."
            ),
        }

    except requests.ConnectionError:
        return {
            "online": False,
            "available": False,
            "model": MODEL,
            "model_available": False,
            "models": [],
            "message": "Ollama is not running.",
        }

    except requests.Timeout:
        return {
            "online": False,
            "available": False,
            "model": MODEL,
            "model_available": False,
            "models": [],
            "message": "Ollama health check timed out.",
        }

    except requests.RequestException as exc:
        LOGGER.warning("Ollama health check failed: %s", exc)

        return {
            "online": False,
            "available": False,
            "model": MODEL,
            "model_available": False,
            "models": [],
            "message": f"Ollama health check failed: {exc}",
        }

    except (ValueError, TypeError) as exc:
        LOGGER.warning("Invalid Ollama health response: %s", exc)

        return {
            "online": True,
            "available": True,
            "model": MODEL,
            "model_available": False,
            "models": [],
            "message": "Ollama returned an invalid health response.",
        }
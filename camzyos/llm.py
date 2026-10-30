"""Shared structured requests with an explicit application token budget."""
import json
from functools import lru_cache

import tiktoken
from openai import OpenAI


class ContextBudgetExceeded(ValueError):
    """Nothing is deleted or silently clipped when a request cannot fit."""


def encode(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)


@lru_cache(maxsize=8)
def tokenizer(model):
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("o200k_base")


def token_count(cfg, value):
    return len(tokenizer(cfg["model"]).encode(encode(value), disallowed_special=()))


def input_limit(cfg, output_tokens=None):
    return (int(cfg.get("context_window_tokens", 32000))
            - int(output_tokens or cfg["max_output_tokens"])
            - int(cfg.get("context_safety_margin_tokens", 1024)))


def request_tokens(cfg, schema, instruction, payload):
    # Includes the structured schema and conservative message framing overhead.
    return token_count(cfg, {"system": instruction, "user": payload,
                             "schema": schema.model_json_schema()}) + 32


def structured(cfg, schema, instruction, payload, *, output_tokens=None):
    output_tokens = output_tokens or cfg["max_output_tokens"]
    if request_tokens(cfg, schema, instruction, payload) > input_limit(cfg, output_tokens):
        raise ContextBudgetExceeded("Request exceeds the configured working-context budget.")
    with OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"], timeout=60, max_retries=1) as client:
        response = client.responses.parse(model=cfg["model"], store=False, max_output_tokens=output_tokens,
            input=[{"role": "system", "content": instruction}, {"role": "user", "content": encode(payload)}],
            text_format=schema)
    if response.output_parsed is None:
        raise ValueError("Model returned no structured result.")
    return response.output_parsed

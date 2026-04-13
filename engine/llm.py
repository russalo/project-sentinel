"""Thin OpenAI client wrapper.

Builds a client from a Config. Does not read os.environ. Does not
cache a global client — callers can memoize if they need to. Exists
so agent modules don't import the openai SDK directly, which makes
mocking and provider swaps cheaper down the line.
"""

from openai import OpenAI

from .types import Config


def build_client(config: Config) -> OpenAI:
    kwargs: dict = {"api_key": config.openai_api_key}
    if config.openai_base_url:
        kwargs["base_url"] = config.openai_base_url
    return OpenAI(**kwargs)

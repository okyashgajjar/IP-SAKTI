"""
LLM Provider Factory.
Reads .env and returns the correct LangChain ChatModel.
Supports: Google Gemini, OpenAI, OpenRouter.
"""
import os
from dotenv import load_dotenv

load_dotenv(override=True)


def get_llm():
    """Return the configured LLM based on .env LLM_PROVIDER."""
    provider = os.getenv("LLM_PROVIDER", "google")
    model = os.getenv("LLM_MODEL", "gemini-2.0-flash")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.1"))

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )

    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=os.getenv("OPENAI_API_KEY"),
        )

    elif provider == "openrouter":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            timeout=60,
            max_retries=2,
        )

    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")

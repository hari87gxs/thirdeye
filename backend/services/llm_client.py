"""LLM client wrapper for Azure OpenAI API."""
import logging
from openai import AzureOpenAI
from config import settings

logger = logging.getLogger("ThirdEye.LLM")

_client = None


def get_client() -> AzureOpenAI:
    """Get or create Azure OpenAI client singleton."""
    global _client
    if _client is None:
        _client = AzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_version=settings.AZURE_OPENAI_API_VERSION,
        )
        logger.info("Azure OpenAI client initialized (endpoint=%s)", settings.AZURE_OPENAI_ENDPOINT)
    return _client


def chat_completion(
    messages: list[dict],
    deployment: str = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    response_format: dict = None,
) -> str:
    """Send a chat completion request and return the response text."""
    client = get_client()
    kwargs = {
        "model": deployment or settings.AZURE_OPENAI_DEPLOYMENT,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        kwargs["response_format"] = response_format

    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content.strip()


def chat_completion_with_image(
    prompt: str,
    image_base64: str,
    deployment: str = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> str:
    """Send a chat completion with an image and return the response text."""
    client = get_client()
    response = client.chat.completions.create(
        model=deployment or settings.AZURE_OPENAI_VISION_DEPLOYMENT,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                    },
                ],
            }
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()

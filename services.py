
# Standard library imports
import os
import logging
import re

# Third-party imports
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# --- Configuration Variables ---
OPENAI_AZURE_ENDPOINT = os.getenv("OPENAI_AZURE_ENDPOINT", "https://customwrapper1.openai.azure.com/openai/v1")
OPENAI_AZURE_API_KEY = os.getenv("OPENAI_AZURE_API_KEY")
OPENAI_AZURE_DEPLOYMENT = os.getenv("OPENAI_AZURE_DEPLOYMENT", "gpt-5-nano")

MARKDOWN_EXTENSIONS = ['codehilite', 'fenced_code', 'tables', 'extra', 'toc', 'sane_lists']


def _clean_markdown_response(text: str) -> str:
    """
    Clean up markdown response text by removing unwanted labels and formatting.
    """
    if not text:
        return text
    # Remove "markdown" labels at the beginning
    text = re.sub(r'^\s*markdown\s*\n?', '', text, flags=re.IGNORECASE | re.MULTILINE)
    # Remove code block markers if the entire response is wrapped in them
    text = re.sub(r'^```markdown\s*\n?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^```\s*\n?', '', text)
    text = re.sub(r'\n?```\s*$', '', text)
    # Clean up extra whitespace
    text = text.strip()
    return text


logger = logging.getLogger(__name__)


def get_openai_response(
    prompt: str,
    system_message: str = "Respond directly to the user's request. Use markdown formatting for emphasis, but do not include the word 'markdown' in your response. Be conversational and helpful.",
    messages: list = None,
) -> str:
    """
    Process a prompt using the OpenAI client pointed at a custom Azure endpoint
    and return the response text.
    Configured via OPENAI_AZURE_ENDPOINT, OPENAI_AZURE_API_KEY, OPENAI_AZURE_DEPLOYMENT.
    """
    if not prompt or not prompt.strip():
        return "Error: Prompt cannot be empty. Please provide a valid prompt."

    api_key = OPENAI_AZURE_API_KEY
    endpoint = OPENAI_AZURE_ENDPOINT
    deployment = OPENAI_AZURE_DEPLOYMENT

    if not api_key:
        return "Error: OPENAI_AZURE_API_KEY is not set. Please set it in your environment."

    try:
        client = OpenAI(base_url=endpoint, api_key=api_key)
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {e}")
        return "Error: Failed to initialize OpenAI client. Check your endpoint and API key."

    logger.info(f"Processing prompt via OpenAI client: {prompt[:50]}{'...' if len(prompt) > 50 else ''}")

    try:
        if messages:
            # Pre-built messages list (thread context) — append current prompt as final user turn
            full_messages = [{"role": "system", "content": system_message}] + messages + [{"role": "user", "content": prompt}]
        else:
            full_messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ]
        completion = client.chat.completions.create(
            model=deployment,
            messages=full_messages,
            max_completion_tokens=128000,
        )
        response_text = completion.choices[0].message.content or ""
        logger.info("Successfully received OpenAI response.")
        return _clean_markdown_response(response_text)
    except Exception as e:
        logger.error(f"Error calling OpenAI endpoint: {e}")
        return "Error: Failed to process your request. Please try again later or contact support if the issue persists."


if __name__ == "__main__":
    test_prompt = "Explain the theory of relativity in simple terms."
    response = get_openai_response(test_prompt)
    print("AI Response:")
    print(response)
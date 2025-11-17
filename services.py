import os
import uuid
import time
import hashlib
import logging
from datetime import datetime
from dotenv import load_dotenv
from azure.ai.inference import ChatCompletionsClient
from azure.core.credentials import AzureKeyCredential
from azure.ai.inference.models import AssistantMessage, SystemMessage, UserMessage
from typing import Optional

# Markdown parsing
import markdown
import re

# Load environment variables
load_dotenv()

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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

"""
model name: model-router-2
"""
def get_azure_ai_response_model_router2(prompt: str, system_message: str = "Respond directly to the user's request. Use markdown formatting for emphasis, but do not include the word 'markdown' in your response. Be conversational and helpful.") -> str:
    """
    Process a prompt using Azure AI and return the response text.
    
    Args:
        prompt (str): The prompt to process
        system_message (str): System message to guide the AI's behavior
    
    Returns:
        str: The AI response text
    
    Raises:
        ValueError: If AZURE_API_KEY is not set or prompt is empty
        Exception: If Azure AI service call fails
    """

    # Validate input
    if not prompt or not prompt.strip():
        return "Error: Prompt cannot be empty. Please provide a valid prompt."

    # Get Azure API key from environment
    api_key = os.getenv("AZURE_API_KEY")
    if not api_key:
        return "Error: Azure API key is not set. Please set the AZURE_API_KEY environment variable."

    # Initialize Azure AI client
    endpoint = "https://bnagi-mguvo5k5-eastus2.cognitiveservices.azure.com/openai/deployments/model-router-2"
    model_name = "model-router-2"
    api_version = "2024-12-01-preview"

    MARKDOWN_EXTENSIONS = ['codehilite', 'fenced_code', 'tables', 'extra', 'toc', 'sane_lists']

    try:
        client = ChatCompletionsClient(
            api_version=api_version,
            endpoint=endpoint,
            credential=AzureKeyCredential(api_key)
        )
    except Exception as e:
        logger.error(f"Failed to initialize Azure AI client: {e}")
        return "Error: Failed to connect to Azure AI service. Please check your API key and endpoint configuration."

    logger.info(f"Processing prompt: {prompt[:50]}{'...' if len(prompt) > 50 else ''}")

    try:
        # Call Azure AI service with streaming and updated message format
        response = client.complete(
            stream=True,
            messages=[
                SystemMessage(content=system_message + " \n\n "
                "<rule>"
                "<supported_formats>"
                """<b>bold</b>, <strong>bold</strong>
                <i>italic</i>, <em>italic</em>
                <u>underline</u>, <ins>underline</ins>
                <s>strikethrough</s>, <strike>strikethrough</strike>, <del>strikethrough</del>
                <span class="tg-spoiler">spoiler</span>, <tg-spoiler>spoiler</tg-spoiler>
                <b>bold <i>italic bold <s>italic bold strikethrough <span class="tg-spoiler">italic bold strikethrough spoiler</span></s> <u>underline italic bold</u></i> bold</b>
                <a href="http://www.example.com/">inline URL</a>
                <a href="tg://user?id=123456789">inline mention of a user</a>
                <tg-emoji emoji-id="5368324170671202286">👍</tg-emoji>
                <code>inline fixed-width code</code>
                <pre>pre-formatted fixed-width code block</pre>
                <pre><code class="language-python">pre-formatted fixed-width code block written in the Python programming language</code></pre>
                <blockquote>Block quotation started\nBlock quotation continued\nThe last line of the block quotation</blockquote>
                <blockquote expandable>Expandable block quotation started\nExpandable block quotation continued\nExpandable block quotation continued\nHidden by default part of the block quotation started\nExpandable block quotation continued\nThe last line of the block quotation</blockquote>
                
                Please note:

                Any character with code between 1 and 126 inclusively can be escaped anywhere with a preceding '\' character, in which case it is treated as an ordinary character and not a part of the markup. This implies that '\' character usually must be escaped with a preceding '\' character.
                Inside pre and code entities, all '`' and '\' characters must be escaped with a preceding '\' character.
                Inside the (...) part of the inline link and custom emoji definition, all ')' and '\' must be escaped with a preceding '\' character.
                In all other places characters '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!' must be escaped with the preceding character '\'.
                In case of ambiguity between italic and underline entities __ is always greedily treated from left to right as beginning or end of an underline entity, so instead of ___italic underline___ use ___italic underline_**__, adding an empty bold entity as a separator.
                A valid emoji must be provided as an alternative value for the custom emoji. The emoji will be shown instead of the custom emoji in places where a custom emoji cannot be displayed (e.g., system notifications) or if the message is forwarded by a non-premium user. It is recommended to use the emoji from the emoji field of the custom emoji sticker.
                Custom emoji entities can only be used by bots that purchased additional usernames on Fragment.

                
                """
                "</supported_formats>"
                "Respond only with markdown formatted text."
                "</rule>"
                ),
                UserMessage(content=prompt)
            ],
            model=model_name,
            max_tokens=32768,
            temperature=0.7,
            top_p=0.95,
            frequency_penalty=0.0,
            presence_penalty=0.0
        )

        # Collect streaming response text
        response_text = ""
        for update in response:
            if update.choices:
                content = update.choices[0].delta.content or ""
                response_text += content
                # Log content at debug level since it can be verbose
                if content.strip():
                    logger.debug(f"Streaming content: {content[:100]}{'...' if len(content) > 100 else ''}")

        # Clean up client connection
        client.close()
        logger.info("Successfully received AI response.")

        # Clean up the response text
        cleaned_response = _clean_markdown_response(response_text)
        
        return cleaned_response
    except Exception as e:
        # Ensure client is closed even on error
        try:
            client.close()
        except:
            pass
        logger.error(f"Error processing prompt: {str(e)}")
        return "Error: Failed to process your request. Please try again later or contact support if the issue persists."



# if __name__ == "__main__":
#     test_prompt = "Explain the theory of relativity in simple terms."
#     response = get_azure_ai_response_model_router2(test_prompt)
#     print("AI Response:")
#     print(response)
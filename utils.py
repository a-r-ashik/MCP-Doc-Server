"""
utils.py — shared helpers for the MCP documentation server.

Changes from original:
  - get_response_from_llm: default model updated to a currently valid Groq model
  - clean_html_to_txt: returns empty string (not None) on failure so callers
    can do a simple truthiness check
  - Added type hints throughout
"""

import os
import logging

import trafilatura
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
logger = logging.getLogger(__name__)


def clean_html_to_txt(html: str) -> str:
    """
    Extract readable text from raw HTML using trafilatura.
    Returns an empty string if extraction fails or produces nothing.
    """
    if not html:
        return ""
    try:
        extracted = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,   
            favor_recall=True,     
        )
        return extracted or ""
    except Exception as exc:
        logger.warning("trafilatura extraction failed: %s", exc)
        return ""


def get_response_from_llm(
    user_prompt: str,
    system_prompt: str,
    model: str = "llama-3.3-70b-versatile",  
) -> str:
    """
    Send a prompt to the Groq API and return the assistant's reply.

    Args:
        user_prompt:   The user message / content to process.
        system_prompt: Instruction for the model.
        model:         Groq model ID. Defaults to llama-3.3-70b-versatile.

    Returns:
        The model's response text, or an empty string on failure.
    """
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        logger.error("GROQ_API_KEY not set in environment / .env file")
        return ""

    try:
        client = Groq(api_key=api_key)
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            model=model,
            temperature=0.1,  
        )
        return chat_completion.choices[0].message.content or ""
    except Exception as exc:
        logger.error("Groq API call failed: %s", exc)
        return ""

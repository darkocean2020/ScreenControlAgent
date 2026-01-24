"""VLM and LLM client implementations for Claude and OpenAI."""

import base64
from abc import ABC, abstractmethod
from io import BytesIO
from typing import Optional

from PIL import Image


class LLMClient(ABC):
    """Abstract base class for text-only LLM clients (reasoning/planning)."""

    @abstractmethod
    def reason(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Generate reasoning/planning based on text input.

        Args:
            prompt: User prompt with perception data
            system_prompt: Optional system prompt

        Returns:
            Model response text
        """
        pass


class VLMClient(ABC):
    """Abstract base class for VLM clients."""

    @abstractmethod
    def analyze_screen(
        self,
        screenshot: Image.Image,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Analyze a screenshot with the given prompt.

        Args:
            screenshot: PIL Image object
            prompt: User prompt
            system_prompt: Optional system prompt

        Returns:
            Model response text
        """
        pass

    def _image_to_base64(self, image: Image.Image, format: str = "PNG") -> str:
        """Convert PIL Image to base64 string."""
        buffer = BytesIO()
        image.save(buffer, format=format)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")


class ClaudeVLMClient(VLMClient):
    """Claude API client for vision tasks."""

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):
        """
        Initialize Claude client.

        Args:
            api_key: Anthropic API key
            model: Model name to use
        """
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def analyze_screen(
        self,
        screenshot: Image.Image,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> str:
        """Analyze screenshot using Claude."""
        image_data = self._image_to_base64(screenshot)

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_data
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ]

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt or "",
            messages=messages
        )

        return response.content[0].text


class OpenAIVLMClient(VLMClient):
    """OpenAI GPT-4o client for vision tasks."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        """
        Initialize OpenAI client.

        Args:
            api_key: OpenAI API key
            model: Model name to use
        """
        import openai
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model

    def analyze_screen(
        self,
        screenshot: Image.Image,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> str:
        """Analyze screenshot using GPT-4o."""
        image_data = self._image_to_base64(screenshot)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_data}"
                    }
                },
                {
                    "type": "text",
                    "text": prompt
                }
            ]
        })

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=4096
        )

        return response.choices[0].message.content


# ============================================================================
# LLM Clients (Text-only, for reasoning/planning)
# ============================================================================

class ClaudeLLMClient(LLMClient):
    """Claude API client for text-only reasoning tasks."""

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):
        """
        Initialize Claude LLM client.

        Args:
            api_key: Anthropic API key
            model: Model name to use
        """
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def reason(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> str:
        """Generate reasoning using Claude (text-only)."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system_prompt or "",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text


class OpenAILLMClient(LLMClient):
    """OpenAI client for text-only reasoning tasks."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        """
        Initialize OpenAI LLM client.

        Args:
            api_key: OpenAI API key
            model: Model name to use (gpt-4o, gpt-4o-mini, etc.)
        """
        import openai
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model

    def reason(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> str:
        """Generate reasoning using OpenAI (text-only)."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=1024
        )
        return response.choices[0].message.content

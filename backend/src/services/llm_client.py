"""
LLM client per T093
OpenAI-compatible API client
Supports local and SaaS endpoints per research.md
"""
import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)


logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """LLM provider types"""
    OPENAI = "openai"
    LOCAL = "local"
    AZURE = "azure"


@dataclass
class LLMConfig:
    """
    Configuration for LLM client

    Attributes:
        provider: LLM provider type
        api_key: API key for authentication (optional for local)
        base_url: Base URL for API endpoint
        model: Model name/identifier
        max_tokens: Maximum tokens in response
        temperature: Sampling temperature (0-2)
        timeout_seconds: Request timeout
        max_retries: Maximum retry attempts
    """
    provider: LLMProvider
    api_key: Optional[str] = None
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4"
    max_tokens: int = 2000
    temperature: float = 0.3
    timeout_seconds: int = 60
    max_retries: int = 3


class LLMError(Exception):
    """Base exception for LLM errors"""
    pass


class LLMRateLimitError(LLMError):
    """Rate limit exceeded"""
    pass


class LLMValidationError(LLMError):
    """Response validation failed"""
    pass


class LLMClient:
    """
    OpenAI-compatible LLM API client

    Per research.md §8: Supports both OpenAI SaaS and local LLM endpoints
    Implements retry logic with exponential backoff for resilience

    Usage:
        config = LLMConfig(
            provider=LLMProvider.LOCAL,
            base_url="http://localhost:8000/v1",
            model="mistral-7b"
        )
        client = LLMClient(config)
        response = await client.chat_completion(messages, schema)
    """

    def __init__(self, config: LLMConfig):
        """
        Initialize LLM client

        Args:
            config: LLM configuration
        """
        self.config = config
        self.client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.timeout_seconds),
            headers=self._build_headers()
        )

        logger.info(
            f"Initialized LLM client: provider={config.provider.value}, "
            f"model={config.model}, base_url={config.base_url}"
        )

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers"""
        headers = {
            "Content-Type": "application/json"
        }

        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        return headers

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True
    )
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        response_schema: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Call chat completion API with retry logic

        Args:
            messages: List of message dicts with "role" and "content"
            response_schema: Optional JSON schema for structured output
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            API response dictionary

        Raises:
            LLMError: On API errors
            LLMRateLimitError: On rate limit errors
            LLMValidationError: On response validation errors
        """
        # Build request payload
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
        }

        # Add response format for structured output
        if response_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "strict": True,
                    "schema": response_schema
                }
            }

        try:
            logger.debug(f"Calling LLM API: model={self.config.model}, messages={len(messages)}")

            response = await self.client.post(
                "/chat/completions",
                json=payload
            )

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning(f"Rate limit hit, retry after {retry_after}s")
                raise LLMRateLimitError(f"Rate limit exceeded, retry after {retry_after}s")

            # Handle client errors
            if response.status_code >= 400 and response.status_code < 500:
                error_detail = response.json() if response.content else {}
                logger.error(f"LLM API client error: {response.status_code} - {error_detail}")
                raise LLMError(f"API error {response.status_code}: {error_detail}")

            # Handle server errors (will trigger retry)
            if response.status_code >= 500:
                logger.error(f"LLM API server error: {response.status_code}")
                raise LLMError(f"Server error {response.status_code}")

            response.raise_for_status()
            result = response.json()

            logger.info(
                f"LLM completion successful: "
                f"tokens={result.get('usage', {}).get('total_tokens', 0)}, "
                f"finish_reason={result['choices'][0].get('finish_reason')}"
            )

            return result

        except httpx.TimeoutException as e:
            logger.error(f"LLM API timeout after {self.config.timeout_seconds}s")
            raise LLMError(f"Request timeout: {str(e)}")

        except httpx.NetworkError as e:
            logger.error(f"LLM API network error: {str(e)}")
            raise LLMError(f"Network error: {str(e)}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {str(e)}")
            raise LLMError(f"Invalid JSON response: {str(e)}")

    async def completion(
        self,
        prompt: str,
        response_schema: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Convenience method for single-turn completion

        Args:
            prompt: User prompt
            response_schema: Optional JSON schema
            **kwargs: Additional parameters

        Returns:
            API response dictionary
        """
        messages = [
            {
                "role": "user",
                "content": prompt
            }
        ]

        return await self.chat_completion(messages, response_schema, **kwargs)

    def extract_content(self, response: Dict[str, Any]) -> str:
        """
        Extract content from API response

        Args:
            response: API response dictionary

        Returns:
            Response content string

        Raises:
            LLMError: If response format is invalid
        """
        try:
            return response["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            logger.error(f"Invalid response format: {str(e)}")
            raise LLMError(f"Invalid response format: {str(e)}")

    def extract_json(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract and parse JSON content from response

        Args:
            response: API response dictionary

        Returns:
            Parsed JSON dictionary

        Raises:
            LLMValidationError: If JSON parsing fails
        """
        content = self.extract_content(response)

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM response: {str(e)}")
            raise LLMValidationError(f"Invalid JSON in response: {str(e)}")

    def get_usage(self, response: Dict[str, Any]) -> Dict[str, int]:
        """
        Extract token usage from response

        Args:
            response: API response dictionary

        Returns:
            Usage dictionary with prompt_tokens, completion_tokens, total_tokens
        """
        return response.get("usage", {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        })

    async def close(self) -> None:
        """Close HTTP client"""
        await self.client.aclose()
        logger.info("LLM client closed")

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

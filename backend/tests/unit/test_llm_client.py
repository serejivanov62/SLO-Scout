"""
Unit tests for LLM client (T093)
Tests OpenAI-compatible API client with retry logic
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch
import httpx

from src.services.llm_client import (
    LLMClient,
    LLMConfig,
    LLMProvider,
    LLMError,
    LLMRateLimitError,
    LLMValidationError
)


@pytest.fixture
def llm_config():
    """Create test LLM configuration"""
    return LLMConfig(
        provider=LLMProvider.LOCAL,
        base_url="http://localhost:8000/v1",
        model="test-model",
        api_key="test-key",
        timeout_seconds=10,
        max_retries=3
    )


@pytest.fixture
def llm_client(llm_config):
    """Create LLM client instance"""
    return LLMClient(llm_config)


@pytest.fixture
def mock_response():
    """Mock successful API response"""
    return {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1699200000,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"result": "test"}'
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30
        }
    }


class TestLLMClient:
    """Test LLM client functionality"""

    @pytest.mark.asyncio
    async def test_chat_completion_success(self, llm_client, mock_response):
        """Test successful chat completion"""
        messages = [
            {"role": "user", "content": "Test prompt"}
        ]

        with patch.object(llm_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = Mock(
                status_code=200,
                json=Mock(return_value=mock_response)
            )

            response = await llm_client.chat_completion(messages)

            assert response == mock_response
            assert response['usage']['total_tokens'] == 30
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_completion_with_schema(self, llm_client, mock_response):
        """Test chat completion with JSON schema"""
        messages = [{"role": "user", "content": "Test"}]
        schema = {
            "type": "object",
            "properties": {"result": {"type": "string"}},
            "required": ["result"]
        }

        with patch.object(llm_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = Mock(
                status_code=200,
                json=Mock(return_value=mock_response)
            )

            response = await llm_client.chat_completion(messages, response_schema=schema)

            # Verify schema was passed in request
            call_args = mock_post.call_args
            payload = call_args[1]['json']
            assert 'response_format' in payload
            assert payload['response_format']['type'] == 'json_schema'

    @pytest.mark.asyncio
    async def test_chat_completion_rate_limit(self, llm_client):
        """Test rate limit handling"""
        messages = [{"role": "user", "content": "Test"}]

        with patch.object(llm_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = Mock(
                status_code=429,
                headers={"Retry-After": "60"},
                json=Mock(return_value={"error": "rate_limit"})
            )

            with pytest.raises(LLMRateLimitError) as exc_info:
                await llm_client.chat_completion(messages)

            assert "retry after 60s" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_chat_completion_client_error(self, llm_client):
        """Test client error handling (4xx)"""
        messages = [{"role": "user", "content": "Test"}]

        with patch.object(llm_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = Mock(
                status_code=400,
                content=b'{"error": "invalid_request"}',
                json=Mock(return_value={"error": "invalid_request"})
            )

            with pytest.raises(LLMError) as exc_info:
                await llm_client.chat_completion(messages)

            assert "400" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_chat_completion_server_error(self, llm_client):
        """Test server error handling (5xx)"""
        messages = [{"role": "user", "content": "Test"}]

        with patch.object(llm_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = Mock(
                status_code=500,
                content=b'Internal Server Error'
            )

            with pytest.raises(LLMError) as exc_info:
                await llm_client.chat_completion(messages)

            assert "500" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_chat_completion_timeout(self, llm_client):
        """Test timeout handling"""
        messages = [{"role": "user", "content": "Test"}]

        with patch.object(llm_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Request timeout")

            with pytest.raises(LLMError) as exc_info:
                await llm_client.chat_completion(messages)

            assert "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_chat_completion_network_error(self, llm_client):
        """Test network error handling"""
        messages = [{"role": "user", "content": "Test"}]

        with patch.object(llm_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.NetworkError("Connection failed")

            with pytest.raises(LLMError) as exc_info:
                await llm_client.chat_completion(messages)

            assert "network error" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_completion_convenience_method(self, llm_client, mock_response):
        """Test single-turn completion convenience method"""
        with patch.object(llm_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = Mock(
                status_code=200,
                json=Mock(return_value=mock_response)
            )

            response = await llm_client.completion("Test prompt")

            assert response == mock_response
            # Verify messages were constructed correctly
            call_args = mock_post.call_args
            payload = call_args[1]['json']
            assert len(payload['messages']) == 1
            assert payload['messages'][0]['role'] == 'user'

    def test_extract_content(self, llm_client, mock_response):
        """Test content extraction from response"""
        content = llm_client.extract_content(mock_response)
        assert content == '{"result": "test"}'

    def test_extract_content_invalid_format(self, llm_client):
        """Test content extraction with invalid response"""
        invalid_response = {"choices": []}

        with pytest.raises(LLMError) as exc_info:
            llm_client.extract_content(invalid_response)

        assert "invalid response format" in str(exc_info.value).lower()

    def test_extract_json(self, llm_client, mock_response):
        """Test JSON extraction and parsing"""
        result = llm_client.extract_json(mock_response)
        assert result == {"result": "test"}

    def test_extract_json_invalid(self, llm_client):
        """Test JSON extraction with invalid JSON"""
        invalid_response = {
            "choices": [
                {
                    "message": {
                        "content": "not valid json"
                    }
                }
            ]
        }

        with pytest.raises(LLMValidationError) as exc_info:
            llm_client.extract_json(invalid_response)

        assert "invalid json" in str(exc_info.value).lower()

    def test_get_usage(self, llm_client, mock_response):
        """Test usage extraction"""
        usage = llm_client.get_usage(mock_response)
        assert usage['prompt_tokens'] == 10
        assert usage['completion_tokens'] == 20
        assert usage['total_tokens'] == 30

    def test_get_usage_missing(self, llm_client):
        """Test usage extraction with missing usage data"""
        response = {"choices": []}
        usage = llm_client.get_usage(response)
        assert usage['total_tokens'] == 0

    @pytest.mark.asyncio
    async def test_context_manager(self, llm_config):
        """Test async context manager"""
        async with LLMClient(llm_config) as client:
            assert client.client is not None

        # Client should be closed after exit
        # (httpx.AsyncClient.is_closed would be True)

    def test_headers_with_api_key(self):
        """Test header construction with API key"""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            api_key="sk-test123"
        )
        client = LLMClient(config)
        assert client.client.headers['Authorization'] == 'Bearer sk-test123'

    def test_headers_without_api_key(self):
        """Test header construction without API key"""
        config = LLMConfig(
            provider=LLMProvider.LOCAL,
            base_url="http://localhost:8000/v1"
        )
        client = LLMClient(config)
        assert 'Authorization' not in client.client.headers

    @pytest.mark.asyncio
    async def test_custom_parameters(self, llm_client, mock_response):
        """Test custom temperature and max_tokens"""
        messages = [{"role": "user", "content": "Test"}]

        with patch.object(llm_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = Mock(
                status_code=200,
                json=Mock(return_value=mock_response)
            )

            await llm_client.chat_completion(
                messages,
                temperature=0.7,
                max_tokens=1000
            )

            call_args = mock_post.call_args
            payload = call_args[1]['json']
            assert payload['temperature'] == 0.7
            assert payload['max_tokens'] == 1000


@pytest.mark.asyncio
async def test_llm_client_network_error_handling(llm_config):
    """Test network error is properly caught and wrapped"""
    client = LLMClient(llm_config)
    messages = [{"role": "user", "content": "Test"}]

    with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
        # Simulate network error
        mock_post.side_effect = httpx.NetworkError("Connection failed")

        # Should wrap network error in LLMError
        with pytest.raises(LLMError) as exc_info:
            await client.chat_completion(messages)

        assert "network error" in str(exc_info.value).lower()

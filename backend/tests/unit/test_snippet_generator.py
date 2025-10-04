"""
Unit tests for snippet generator service (T089a)

Tests code snippet generation for instrumentation recommendations.
Target: >= 95% test coverage per T089a requirements.
"""
import pytest
from unittest.mock import Mock, patch

from src.services.snippet_generator import (
    SnippetGenerator,
    CodeSnippet,
)


class TestSnippetGenerator:
    """Test suite for SnippetGenerator"""

    @pytest.fixture
    def generator(self):
        """Create snippet generator instance"""
        return SnippetGenerator()

    def test_initialization(self, generator):
        """Test generator initialization"""
        assert generator is not None
        assert generator.templates is not None
        assert len(generator.templates) > 0
        assert "python_fastapi_rum" in generator.templates

    def test_supported_languages(self, generator):
        """Test supported languages and frameworks"""
        assert "python" in generator.SUPPORTED_LANGUAGES
        assert "javascript" in generator.SUPPORTED_LANGUAGES
        assert "java" in generator.SUPPORTED_LANGUAGES
        assert "go" in generator.SUPPORTED_LANGUAGES

        assert "fastapi" in generator.SUPPORTED_LANGUAGES["python"]
        assert "flask" in generator.SUPPORTED_LANGUAGES["python"]
        assert "django" in generator.SUPPORTED_LANGUAGES["python"]

    # RUM snippet tests
    def test_generate_rum_snippet_python_fastapi(self, generator):
        """Test RUM snippet generation for Python FastAPI"""
        snippet = generator.generate_rum_snippet("python", "fastapi", "test-token-123")

        assert isinstance(snippet, CodeSnippet)
        assert snippet.language == "python"
        assert snippet.framework == "fastapi"
        assert snippet.snippet_type == "enable_rum"
        assert "test-token-123" in snippet.code
        assert "RUMMiddleware" in snippet.code
        assert "FastAPI" in snippet.code
        assert len(snippet.dependencies) > 0
        assert snippet.validation_status is True
        assert len(snippet.validation_errors) == 0

    def test_generate_rum_snippet_no_token(self, generator):
        """Test RUM snippet generation without token"""
        snippet = generator.generate_rum_snippet("python", "fastapi")

        assert "YOUR_RUM_TOKEN_HERE" in snippet.code
        assert snippet.configuration["rum_token"] == "required"

    def test_generate_rum_snippet_unsupported_language(self, generator):
        """Test RUM snippet with unsupported language"""
        with pytest.raises(ValueError) as exc_info:
            generator.generate_rum_snippet("rust", "rocket")

        assert "Unsupported language" in str(exc_info.value)
        assert "rust" in str(exc_info.value)

    def test_generate_rum_snippet_unsupported_framework(self, generator):
        """Test RUM snippet with unsupported framework"""
        with pytest.raises(ValueError) as exc_info:
            generator.generate_rum_snippet("python", "tornado")

        assert "Unsupported framework" in str(exc_info.value)
        assert "tornado" in str(exc_info.value)

    # Request ID snippet tests
    def test_generate_request_id_snippet_python_fastapi(self, generator):
        """Test request ID snippet for Python FastAPI"""
        snippet = generator.generate_request_id_snippet("python", "fastapi")

        assert snippet.language == "python"
        assert snippet.framework == "fastapi"
        assert snippet.snippet_type == "add_request_id"
        assert "X-Request-ID" in snippet.code
        assert "uuid4" in snippet.code
        assert snippet.configuration["header_name"] == "X-Request-ID"
        assert snippet.validation_status is True

    def test_generate_request_id_snippet_custom_header(self, generator):
        """Test request ID snippet with custom header name"""
        snippet = generator.generate_request_id_snippet(
            "python", "fastapi", header_name="X-Trace-ID"
        )

        assert "X-Trace-ID" in snippet.code
        assert snippet.configuration["header_name"] == "X-Trace-ID"

    def test_generate_request_id_snippet_unsupported_language(self, generator):
        """Test request ID snippet with unsupported language"""
        with pytest.raises(ValueError):
            generator.generate_request_id_snippet("ruby", "rails")

    # Sampling snippet tests
    def test_generate_sampling_snippet_python_fastapi(self, generator):
        """Test sampling snippet for Python FastAPI"""
        snippet = generator.generate_sampling_snippet("python", "fastapi", sample_rate=0.1)

        assert snippet.language == "python"
        assert snippet.framework == "fastapi"
        assert snippet.snippet_type == "increase_sampling"
        assert "0.1" in snippet.code
        assert "TraceIdRatioBased" in snippet.code
        assert snippet.configuration["sample_rate"] == "0.1"
        assert snippet.validation_status is True

    def test_generate_sampling_snippet_invalid_rate_too_high(self, generator):
        """Test sampling snippet with invalid rate > 1.0"""
        with pytest.raises(ValueError) as exc_info:
            generator.generate_sampling_snippet("python", "fastapi", sample_rate=1.5)

        assert "between 0.0 and 1.0" in str(exc_info.value)

    def test_generate_sampling_snippet_invalid_rate_negative(self, generator):
        """Test sampling snippet with negative rate"""
        with pytest.raises(ValueError) as exc_info:
            generator.generate_sampling_snippet("python", "fastapi", sample_rate=-0.1)

        assert "between 0.0 and 1.0" in str(exc_info.value)

    def test_generate_sampling_snippet_edge_case_zero(self, generator):
        """Test sampling snippet with 0.0 rate (edge case)"""
        snippet = generator.generate_sampling_snippet("python", "fastapi", sample_rate=0.0)

        assert "0.0" in snippet.code
        assert snippet.validation_status is True

    def test_generate_sampling_snippet_edge_case_one(self, generator):
        """Test sampling snippet with 1.0 rate (edge case)"""
        snippet = generator.generate_sampling_snippet("python", "fastapi", sample_rate=1.0)

        assert "1.0" in snippet.code
        assert snippet.validation_status is True

    # Tracing snippet tests
    def test_generate_tracing_snippet_python_fastapi(self, generator):
        """Test tracing snippet for Python FastAPI"""
        snippet = generator.generate_tracing_snippet(
            "python", "fastapi", otlp_endpoint="http://collector:4317"
        )

        assert snippet.language == "python"
        assert snippet.framework == "fastapi"
        assert snippet.snippet_type == "add_tracing"
        assert "http://collector:4317" in snippet.code
        assert "OTLPSpanExporter" in snippet.code
        assert "FastAPIInstrumentor" in snippet.code
        assert snippet.configuration["otlp_endpoint"] == "http://collector:4317"
        assert snippet.validation_status is True
        assert "opentelemetry" in " ".join(snippet.dependencies)

    def test_generate_tracing_snippet_default_endpoint(self, generator):
        """Test tracing snippet with default endpoint"""
        snippet = generator.generate_tracing_snippet("python", "fastapi")

        assert "http://localhost:4317" in snippet.code

    def test_generate_tracing_snippet_unsupported_framework(self, generator):
        """Test tracing snippet with unsupported framework"""
        with pytest.raises(ValueError):
            generator.generate_tracing_snippet("python", "bottle")

    # Validation tests
    def test_validate_python_syntax_valid(self, generator):
        """Test Python syntax validation with valid code"""
        code = '''
from fastapi import FastAPI

app = FastAPI()
'''
        errors = generator._validate_python_syntax(code)
        assert len(errors) == 0

    def test_validate_python_syntax_invalid(self, generator):
        """Test Python syntax validation with invalid code"""
        code = "def invalid(:"
        errors = generator._validate_python_syntax(code)
        assert len(errors) > 0
        assert "syntax error" in errors[0].lower()

    def test_validate_python_syntax_no_imports(self, generator):
        """Test Python syntax validation without imports"""
        code = "x = 1"
        errors = generator._validate_python_syntax(code)
        assert len(errors) > 0
        assert "import" in errors[0].lower()

    def test_validate_javascript_syntax_valid(self, generator):
        """Test JavaScript syntax validation with valid code"""
        code = '''
const express = require('express');
const app = express();
'''
        errors = generator._validate_javascript_syntax(code)
        assert len(errors) == 0

    def test_validate_javascript_syntax_no_variables(self, generator):
        """Test JavaScript syntax validation without variables"""
        code = "console.log('hello');"
        errors = generator._validate_javascript_syntax(code)
        assert len(errors) > 0
        assert "variable" in errors[0].lower()

    def test_validate_javascript_syntax_no_imports(self, generator):
        """Test JavaScript syntax validation without imports"""
        code = "const x = 1;"
        errors = generator._validate_javascript_syntax(code)
        assert len(errors) > 0
        assert "import" in errors[0].lower()

    def test_validate_java_syntax_valid(self, generator):
        """Test Java syntax validation with valid code"""
        code = '''
package com.example;

import org.springframework.boot.SpringApplication;

public class Application {}
'''
        errors = generator._validate_java_syntax(code)
        assert len(errors) == 0

    def test_validate_java_syntax_no_package(self, generator):
        """Test Java syntax validation without package"""
        code = "import java.util.List;"
        errors = generator._validate_java_syntax(code)
        assert len(errors) > 0
        assert "package" in errors[0].lower()

    def test_validate_go_syntax_valid(self, generator):
        """Test Go syntax validation with valid code"""
        code = '''
package main

import "fmt"
'''
        errors = generator._validate_go_syntax(code)
        assert len(errors) == 0

    def test_validate_go_syntax_no_package(self, generator):
        """Test Go syntax validation without package"""
        code = "func main() {}"
        errors = generator._validate_go_syntax(code)
        assert len(errors) > 0
        assert "package" in errors[0].lower()

    # Security tests
    def test_check_security_issues_clean(self, generator):
        """Test security check with clean code"""
        code = '''
from fastapi import FastAPI

app = FastAPI()
'''
        errors = generator._check_security_issues(code)
        assert len(errors) == 0

    def test_check_security_issues_password(self, generator):
        """Test security check detects hardcoded password"""
        code = 'password = "secret123"'
        errors = generator._check_security_issues(code)
        assert len(errors) > 0
        assert "secret" in errors[0].lower()

    def test_check_security_issues_api_key(self, generator):
        """Test security check detects hardcoded API key"""
        code = 'api_key = "sk-1234567890"'
        errors = generator._check_security_issues(code)
        assert len(errors) > 0
        assert "secret" in errors[0].lower()

    def test_check_security_issues_secret(self, generator):
        """Test security check detects hardcoded secret"""
        code = 'SECRET = "my-secret-value"'
        errors = generator._check_security_issues(code)
        assert len(errors) > 0

    # Dependency tests
    def test_get_rum_dependencies_python_fastapi(self, generator):
        """Test RUM dependencies for Python FastAPI"""
        deps = generator._get_rum_dependencies("python", "fastapi")
        assert len(deps) > 0
        assert "slo-scout-rum" in deps[0]

    def test_get_rum_dependencies_javascript_express(self, generator):
        """Test RUM dependencies for JavaScript Express"""
        deps = generator._get_rum_dependencies("javascript", "express")
        assert len(deps) > 0
        assert "@slo-scout/rum-sdk" in deps[0]

    def test_get_rum_dependencies_unsupported(self, generator):
        """Test RUM dependencies for unsupported framework"""
        deps = generator._get_rum_dependencies("ruby", "rails")
        assert len(deps) == 0

    def test_get_tracing_dependencies_python_fastapi(self, generator):
        """Test tracing dependencies for Python FastAPI"""
        deps = generator._get_tracing_dependencies("python", "fastapi")
        assert len(deps) >= 4
        assert any("opentelemetry-api" in d for d in deps)
        assert any("opentelemetry-sdk" in d for d in deps)
        assert any("opentelemetry-exporter-otlp" in d for d in deps)
        assert any("fastapi" in d for d in deps)

    def test_get_tracing_dependencies_python_flask(self, generator):
        """Test tracing dependencies for Python Flask"""
        deps = generator._get_tracing_dependencies("python", "flask")
        assert any("flask" in d for d in deps)

    def test_get_tracing_dependencies_python_django(self, generator):
        """Test tracing dependencies for Python Django"""
        deps = generator._get_tracing_dependencies("python", "django")
        assert any("django" in d for d in deps)

    # Install instructions tests
    def test_get_install_instructions_python_rum(self, generator):
        """Test install instructions for Python RUM"""
        instructions = generator._get_install_instructions("python", "fastapi", "rum")
        assert "pip install" in instructions
        assert "slo-scout-rum" in instructions

    def test_get_install_instructions_python_tracing(self, generator):
        """Test install instructions for Python tracing"""
        instructions = generator._get_install_instructions("python", "fastapi", "tracing")
        assert "pip install" in instructions
        assert "opentelemetry" in instructions

    def test_get_install_instructions_python_request_id(self, generator):
        """Test install instructions for request ID (no deps)"""
        instructions = generator._get_install_instructions("python", "fastapi", "request_id")
        assert "No additional dependencies" in instructions

    def test_get_install_instructions_javascript(self, generator):
        """Test install instructions for JavaScript"""
        instructions = generator._get_install_instructions("javascript", "express", "rum")
        assert "npm install" in instructions

    # Template tests
    def test_load_templates(self, generator):
        """Test template loading"""
        templates = generator._load_templates()
        assert len(templates) > 0
        assert "python_fastapi_rum" in templates
        assert "python_fastapi_request_id" in templates
        assert "python_fastapi_sampling" in templates
        assert "python_fastapi_tracing" in templates

    def test_get_default_rum_template(self, generator):
        """Test default RUM template generation"""
        template = generator._get_default_rum_template("python", "bottle")
        assert "RUM integration" in template
        assert "bottle" in template
        assert "{{RUM_TOKEN}}" in template

    def test_get_default_request_id_template(self, generator):
        """Test default request ID template generation"""
        template = generator._get_default_request_id_template("python", "bottle")
        assert "Request ID" in template
        assert "bottle" in template

    def test_get_default_sampling_template(self, generator):
        """Test default sampling template generation"""
        template = generator._get_default_sampling_template("python", "bottle")
        assert "sampling" in template.lower()
        assert "{{SAMPLE_RATE}}" in template

    def test_get_default_tracing_template(self, generator):
        """Test default tracing template generation"""
        template = generator._get_default_tracing_template("python", "bottle")
        assert "tracing" in template.lower()
        assert "{{OTLP_ENDPOINT}}" in template

    # Edge cases and error handling
    def test_generate_snippet_all_languages(self, generator):
        """Test snippet generation for all supported languages"""
        for language in generator.SUPPORTED_LANGUAGES:
            frameworks = generator.SUPPORTED_LANGUAGES[language]
            for framework in frameworks:
                # Test RUM snippet
                snippet = generator.generate_rum_snippet(language, framework)
                assert snippet is not None
                assert snippet.language == language
                assert snippet.framework == framework

    def test_snippet_validation_workflow(self, generator):
        """Test complete snippet validation workflow"""
        snippet = generator.generate_rum_snippet("python", "fastapi", "token")

        # Check initial validation
        assert snippet.validation_status is True
        assert len(snippet.validation_errors) == 0

        # Verify code contains expected elements
        assert "from " in snippet.code
        assert "import " in snippet.code

    def test_snippet_metadata_completeness(self, generator):
        """Test snippet metadata is complete"""
        snippet = generator.generate_tracing_snippet("python", "fastapi")

        assert snippet.language is not None
        assert snippet.framework is not None
        assert snippet.snippet_type is not None
        assert snippet.code is not None
        assert snippet.dependencies is not None
        assert snippet.configuration is not None
        assert snippet.install_instructions is not None
        assert isinstance(snippet.validation_status, bool)
        assert isinstance(snippet.validation_errors, list)

    def test_multiple_snippet_generation(self, generator):
        """Test generating multiple snippets in sequence"""
        snippets = []

        # Generate different snippet types
        snippets.append(generator.generate_rum_snippet("python", "fastapi"))
        snippets.append(generator.generate_request_id_snippet("python", "fastapi"))
        snippets.append(generator.generate_sampling_snippet("python", "fastapi"))
        snippets.append(generator.generate_tracing_snippet("python", "fastapi"))

        # Verify all snippets are unique and valid
        assert len(snippets) == 4
        snippet_types = [s.snippet_type for s in snippets]
        assert len(set(snippet_types)) == 4  # All unique types

        for snippet in snippets:
            assert snippet.validation_status is True

    def test_snippet_code_non_empty(self, generator):
        """Test all snippets generate non-empty code"""
        snippet_methods = [
            ("generate_rum_snippet", ["python", "fastapi"]),
            ("generate_request_id_snippet", ["python", "fastapi"]),
            ("generate_sampling_snippet", ["python", "fastapi", 0.1]),
            ("generate_tracing_snippet", ["python", "fastapi"]),
        ]

        for method_name, args in snippet_methods:
            method = getattr(generator, method_name)
            snippet = method(*args)
            assert len(snippet.code) > 0
            assert snippet.code.strip() != ""

    def test_validation_with_no_dependencies(self, generator):
        """Test validation handles snippets with no dependencies (using built-in libs)"""
        snippet = CodeSnippet(
            language="python",
            framework="fastapi",
            snippet_type="test",
            code="from fastapi import FastAPI\napp = FastAPI()",
            dependencies=[],
            configuration={},
            install_instructions="",
            validation_status=False,
            validation_errors=[]
        )

        generator._validate_snippet(snippet)

        # Empty dependencies are allowed for built-in libraries
        # Validation should pass if no syntax or security errors
        assert snippet.validation_status is True
        assert len(snippet.validation_errors) == 0

    def test_configuration_parameter_substitution(self, generator):
        """Test configuration parameters are properly substituted"""
        # Test RUM token substitution
        rum_snippet = generator.generate_rum_snippet("python", "fastapi", "abc123")
        assert "abc123" in rum_snippet.code
        assert "{{RUM_TOKEN}}" not in rum_snippet.code

        # Test header name substitution
        req_id_snippet = generator.generate_request_id_snippet(
            "python", "fastapi", "X-Custom-ID"
        )
        assert "X-Custom-ID" in req_id_snippet.code
        assert "{{HEADER_NAME}}" not in req_id_snippet.code

        # Test sample rate substitution
        sample_snippet = generator.generate_sampling_snippet("python", "fastapi", 0.25)
        assert "0.25" in sample_snippet.code
        assert "{{SAMPLE_RATE}}" not in sample_snippet.code

        # Test endpoint substitution
        trace_snippet = generator.generate_tracing_snippet(
            "python", "fastapi", "http://custom:4317"
        )
        assert "http://custom:4317" in trace_snippet.code
        assert "{{OTLP_ENDPOINT}}" not in trace_snippet.code


class TestCodeSnippet:
    """Test CodeSnippet dataclass"""

    def test_code_snippet_creation(self):
        """Test creating a CodeSnippet instance"""
        snippet = CodeSnippet(
            language="python",
            framework="fastapi",
            snippet_type="enable_rum",
            code="print('hello')",
            dependencies=["pkg1", "pkg2"],
            configuration={"key": "value"},
            install_instructions="pip install pkg1",
            validation_status=True,
            validation_errors=[]
        )

        assert snippet.language == "python"
        assert snippet.framework == "fastapi"
        assert snippet.snippet_type == "enable_rum"
        assert snippet.code == "print('hello')"
        assert len(snippet.dependencies) == 2
        assert snippet.configuration["key"] == "value"
        assert "pip install" in snippet.install_instructions
        assert snippet.validation_status is True
        assert len(snippet.validation_errors) == 0

    def test_code_snippet_with_validation_errors(self):
        """Test CodeSnippet with validation errors"""
        snippet = CodeSnippet(
            language="python",
            framework="fastapi",
            snippet_type="test",
            code="invalid code",
            dependencies=[],
            configuration={},
            install_instructions="",
            validation_status=False,
            validation_errors=["Error 1", "Error 2"]
        )

        assert snippet.validation_status is False
        assert len(snippet.validation_errors) == 2
        assert "Error 1" in snippet.validation_errors


class TestSnippetGeneratorIntegration:
    """Integration tests for snippet generator"""

    @pytest.fixture
    def generator(self):
        return SnippetGenerator()

    def test_full_workflow_rum_integration(self, generator):
        """Test complete RUM integration workflow"""
        # Generate snippet
        snippet = generator.generate_rum_snippet(
            language="python",
            framework="fastapi",
            rum_token="prod-token-xyz"
        )

        # Verify snippet is ready for use
        assert snippet.validation_status is True
        assert len(snippet.validation_errors) == 0
        assert "prod-token-xyz" in snippet.code
        assert len(snippet.dependencies) > 0
        assert "pip install" in snippet.install_instructions

        # Verify code is syntactically valid Python
        try:
            compile(snippet.code, '<string>', 'exec')
        except SyntaxError:
            pytest.fail("Generated code has syntax errors")

    def test_full_workflow_observability_setup(self, generator):
        """Test complete observability setup workflow"""
        # Generate all necessary snippets
        rum = generator.generate_rum_snippet("python", "fastapi", "token")
        req_id = generator.generate_request_id_snippet("python", "fastapi")
        sampling = generator.generate_sampling_snippet("python", "fastapi", 0.1)
        tracing = generator.generate_tracing_snippet("python", "fastapi")

        # Verify all snippets are valid
        snippets = [rum, req_id, sampling, tracing]
        for snippet in snippets:
            assert snippet.validation_status is True
            assert len(snippet.code) > 0

        # Verify unique snippet types
        types = [s.snippet_type for s in snippets]
        assert len(set(types)) == 4

    def test_error_handling_chain(self, generator):
        """Test error handling through the generation chain"""
        # Invalid language
        with pytest.raises(ValueError) as exc:
            generator.generate_rum_snippet("invalid", "framework")
        assert "Unsupported language" in str(exc.value)

        # Invalid framework
        with pytest.raises(ValueError) as exc:
            generator.generate_rum_snippet("python", "invalid")
        assert "Unsupported framework" in str(exc.value)

        # Invalid sample rate
        with pytest.raises(ValueError) as exc:
            generator.generate_sampling_snippet("python", "fastapi", 2.0)
        assert "between 0.0 and 1.0" in str(exc.value)

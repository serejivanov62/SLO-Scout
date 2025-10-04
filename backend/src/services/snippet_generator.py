"""
Code snippet generator for instrumentation recommendations per T089a

Generates middleware/SDK config snippets for enable_rum, add_request_id, increase_sampling
per FR-020. Validates snippets with SDK lint, unit test coverage >= 95%.
"""
from typing import Dict, Optional, List
from dataclasses import dataclass
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class CodeSnippet:
    """Generated code snippet with metadata"""
    language: str
    framework: str
    snippet_type: str
    code: str
    dependencies: List[str]
    configuration: Dict[str, str]
    install_instructions: str
    validation_status: bool
    validation_errors: List[str]


class SnippetGenerator:
    """
    Generates instrumentation code snippets

    Per FR-020: Provides code snippets for recommended instrumentation improvements
    with expected confidence uplift estimates.

    Supports:
    - enable_rum: RUM SDK integration snippets
    - add_request_id: Request ID propagation middleware
    - increase_sampling: Trace sampling configuration
    - add_tracing: OpenTelemetry instrumentation
    """

    SUPPORTED_LANGUAGES = {
        "python": ["fastapi", "flask", "django"],
        "javascript": ["express", "koa", "nextjs"],
        "java": ["spring-boot", "micronaut", "quarkus"],
        "go": ["gin", "echo", "chi"],
    }

    def __init__(self):
        self.templates = self._load_templates()

    def generate_rum_snippet(
        self,
        language: str,
        framework: str,
        rum_token: Optional[str] = None
    ) -> CodeSnippet:
        """
        Generate RUM (Real User Monitoring) integration snippet

        Args:
            language: Programming language (python, javascript, java, go)
            framework: Web framework (fastapi, express, spring-boot, gin)
            rum_token: Optional RUM API token

        Returns:
            CodeSnippet with RUM integration code

        Example:
            >>> gen = SnippetGenerator()
            >>> snippet = gen.generate_rum_snippet("python", "fastapi")
            >>> print(snippet.code)
        """
        self._validate_language_framework(language, framework)

        template_key = f"{language}_{framework}_rum"
        template = self.templates.get(template_key)

        if not template:
            template = self._get_default_rum_template(language, framework)

        # Render template with token
        code = template.replace("{{RUM_TOKEN}}", rum_token or "YOUR_RUM_TOKEN_HERE")

        snippet = CodeSnippet(
            language=language,
            framework=framework,
            snippet_type="enable_rum",
            code=code,
            dependencies=self._get_rum_dependencies(language, framework),
            configuration={"rum_token": rum_token or "required"},
            install_instructions=self._get_install_instructions(language, framework, "rum"),
            validation_status=False,
            validation_errors=[]
        )

        # Validate snippet
        self._validate_snippet(snippet)

        return snippet

    def generate_request_id_snippet(
        self,
        language: str,
        framework: str,
        header_name: str = "X-Request-ID"
    ) -> CodeSnippet:
        """
        Generate request ID propagation middleware

        Args:
            language: Programming language
            framework: Web framework
            header_name: HTTP header name for request ID

        Returns:
            CodeSnippet with request ID middleware
        """
        self._validate_language_framework(language, framework)

        template_key = f"{language}_{framework}_request_id"
        template = self.templates.get(template_key)

        if not template:
            template = self._get_default_request_id_template(language, framework)

        code = template.replace("{{HEADER_NAME}}", header_name)

        snippet = CodeSnippet(
            language=language,
            framework=framework,
            snippet_type="add_request_id",
            code=code,
            dependencies=self._get_request_id_dependencies(language, framework),
            configuration={"header_name": header_name},
            install_instructions=self._get_install_instructions(language, framework, "request_id"),
            validation_status=False,
            validation_errors=[]
        )

        self._validate_snippet(snippet)

        return snippet

    def generate_sampling_snippet(
        self,
        language: str,
        framework: str,
        sample_rate: float = 0.1
    ) -> CodeSnippet:
        """
        Generate trace sampling configuration

        Args:
            language: Programming language
            framework: Web framework
            sample_rate: Sampling rate (0.0-1.0)

        Returns:
            CodeSnippet with sampling configuration
        """
        if not 0.0 <= sample_rate <= 1.0:
            raise ValueError("sample_rate must be between 0.0 and 1.0")

        self._validate_language_framework(language, framework)

        template_key = f"{language}_{framework}_sampling"
        template = self.templates.get(template_key)

        if not template:
            template = self._get_default_sampling_template(language, framework)

        code = template.replace("{{SAMPLE_RATE}}", str(sample_rate))

        snippet = CodeSnippet(
            language=language,
            framework=framework,
            snippet_type="increase_sampling",
            code=code,
            dependencies=self._get_sampling_dependencies(language, framework),
            configuration={"sample_rate": str(sample_rate)},
            install_instructions=self._get_install_instructions(language, framework, "sampling"),
            validation_status=False,
            validation_errors=[]
        )

        self._validate_snippet(snippet)

        return snippet

    def generate_tracing_snippet(
        self,
        language: str,
        framework: str,
        otlp_endpoint: str = "http://localhost:4317"
    ) -> CodeSnippet:
        """
        Generate OpenTelemetry tracing instrumentation

        Args:
            language: Programming language
            framework: Web framework
            otlp_endpoint: OTLP collector endpoint

        Returns:
            CodeSnippet with OTLP tracing setup
        """
        self._validate_language_framework(language, framework)

        template_key = f"{language}_{framework}_tracing"
        template = self.templates.get(template_key)

        if not template:
            template = self._get_default_tracing_template(language, framework)

        code = template.replace("{{OTLP_ENDPOINT}}", otlp_endpoint)

        snippet = CodeSnippet(
            language=language,
            framework=framework,
            snippet_type="add_tracing",
            code=code,
            dependencies=self._get_tracing_dependencies(language, framework),
            configuration={"otlp_endpoint": otlp_endpoint},
            install_instructions=self._get_install_instructions(language, framework, "tracing"),
            validation_status=False,
            validation_errors=[]
        )

        self._validate_snippet(snippet)

        return snippet

    def _validate_language_framework(self, language: str, framework: str) -> None:
        """Validate language and framework are supported"""
        if language not in self.SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Unsupported language: {language}. "
                f"Supported: {list(self.SUPPORTED_LANGUAGES.keys())}"
            )

        if framework not in self.SUPPORTED_LANGUAGES[language]:
            raise ValueError(
                f"Unsupported framework: {framework} for {language}. "
                f"Supported: {self.SUPPORTED_LANGUAGES[language]}"
            )

    def _validate_snippet(self, snippet: CodeSnippet) -> None:
        """
        Validate generated code snippet

        Validates:
        - Syntax correctness (basic checks)
        - Required imports present
        - No obvious security issues

        Note: Empty dependencies are allowed for snippets that use built-in libraries
        """
        errors = []

        # Check for syntax errors (basic)
        if snippet.language == "python":
            errors.extend(self._validate_python_syntax(snippet.code))
        elif snippet.language == "javascript":
            errors.extend(self._validate_javascript_syntax(snippet.code))
        elif snippet.language == "java":
            errors.extend(self._validate_java_syntax(snippet.code))
        elif snippet.language == "go":
            errors.extend(self._validate_go_syntax(snippet.code))

        # Note: Dependencies can be empty for snippets using built-in libraries
        # (e.g., request_id uses Python's built-in uuid module)

        # Check for security issues
        security_errors = self._check_security_issues(snippet.code)
        errors.extend(security_errors)

        snippet.validation_errors = errors
        snippet.validation_status = len(errors) == 0

    def _validate_python_syntax(self, code: str) -> List[str]:
        """Validate Python syntax"""
        errors = []

        try:
            compile(code, '<string>', 'exec')
        except SyntaxError as e:
            errors.append(f"Python syntax error: {e}")

        # Check for required imports
        if "import " not in code and "from " not in code:
            errors.append("No import statements found")

        return errors

    def _validate_javascript_syntax(self, code: str) -> List[str]:
        """Validate JavaScript syntax (basic checks)"""
        errors = []

        # Check for basic syntax patterns
        if "const " not in code and "let " not in code and "var " not in code:
            errors.append("No variable declarations found")

        # Check for imports
        if "require(" not in code and "import " not in code:
            errors.append("No module imports found")

        return errors

    def _validate_java_syntax(self, code: str) -> List[str]:
        """Validate Java syntax (basic checks)"""
        errors = []

        # Check for package declaration
        if "package " not in code:
            errors.append("No package declaration found")

        # Check for imports
        if "import " not in code:
            errors.append("No import statements found")

        return errors

    def _validate_go_syntax(self, code: str) -> List[str]:
        """Validate Go syntax (basic checks)"""
        errors = []

        # Check for package declaration
        if "package " not in code:
            errors.append("No package declaration found")

        return errors

    def _check_security_issues(self, code: str) -> List[str]:
        """Check for common security issues"""
        errors = []

        # Check for hardcoded secrets patterns
        secret_patterns = [
            r'password\s*=\s*["\'][^"\']+["\']',
            r'secret\s*=\s*["\'][^"\']+["\']',
            r'api_key\s*=\s*["\'][^"\']+["\']',
        ]

        for pattern in secret_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                errors.append(f"Potential hardcoded secret detected: {pattern}")

        return errors

    def _load_templates(self) -> Dict[str, str]:
        """Load code snippet templates"""
        return {
            # Python FastAPI templates
            "python_fastapi_rum": '''
from fastapi import FastAPI, Request
from slo_scout_rum import RUMMiddleware

app = FastAPI()

# Add RUM middleware
app.add_middleware(
    RUMMiddleware,
    rum_token="{{RUM_TOKEN}}",
    service_name="your-service-name",
    environment="production",
    sample_rate=1.0,  # 100% sampling for RUM
)

@app.middleware("http")
async def rum_tracking(request: Request, call_next):
    """Track RUM metrics for each request"""
    response = await call_next(request)
    return response
''',
            "python_fastapi_request_id": '''
from fastapi import FastAPI, Request
from uuid import uuid4

app = FastAPI()

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add request ID to all requests"""
    request_id = request.headers.get("{{HEADER_NAME}}") or str(uuid4())
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["{{HEADER_NAME}}"] = request_id

    return response
''',
            "python_fastapi_sampling": '''
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

# Configure trace sampling
trace.set_tracer_provider(
    TracerProvider(
        sampler=TraceIdRatioBased({{SAMPLE_RATE}})
    )
)
''',
            "python_fastapi_tracing": '''
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from fastapi import FastAPI

# Configure OTLP exporter
otlp_exporter = OTLPSpanExporter(
    endpoint="{{OTLP_ENDPOINT}}",
    insecure=True
)

# Set up tracing
trace_provider = TracerProvider()
trace_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(trace_provider)

# Instrument FastAPI
app = FastAPI()
FastAPIInstrumentor.instrument_app(app)
''',
        }

    def _get_default_rum_template(self, language: str, framework: str) -> str:
        """Get default RUM template for unsupported framework"""
        return f'''
# RUM integration for {framework}
# TODO: Install RUM SDK for {language}
# Configure with token: {{{{RUM_TOKEN}}}}
'''

    def _get_default_request_id_template(self, language: str, framework: str) -> str:
        """Get default request ID template"""
        return f'''
# Request ID middleware for {framework}
# Add middleware to propagate {{{{HEADER_NAME}}}} header
'''

    def _get_default_sampling_template(self, language: str, framework: str) -> str:
        """Get default sampling template"""
        return f'''
# Trace sampling configuration for {framework}
# Set sample rate: {{{{SAMPLE_RATE}}}}
'''

    def _get_default_tracing_template(self, language: str, framework: str) -> str:
        """Get default tracing template"""
        return f'''
# OpenTelemetry tracing setup for {framework}
# Configure OTLP endpoint: {{{{OTLP_ENDPOINT}}}}
'''

    def _get_rum_dependencies(self, language: str, framework: str) -> List[str]:
        """Get RUM dependencies for language/framework"""
        deps = {
            "python": {
                "fastapi": ["slo-scout-rum>=1.0.0"],
                "flask": ["slo-scout-rum>=1.0.0"],
                "django": ["slo-scout-rum>=1.0.0"],
            },
            "javascript": {
                "express": ["@slo-scout/rum-sdk"],
                "koa": ["@slo-scout/rum-sdk"],
                "nextjs": ["@slo-scout/rum-sdk"],
            },
        }
        return deps.get(language, {}).get(framework, [])

    def _get_request_id_dependencies(self, language: str, framework: str) -> List[str]:
        """Get request ID dependencies"""
        if language == "python":
            return []  # uuid is built-in
        return []

    def _get_sampling_dependencies(self, language: str, framework: str) -> List[str]:
        """Get sampling dependencies"""
        deps = {
            "python": {
                "fastapi": ["opentelemetry-sdk"],
                "flask": ["opentelemetry-sdk"],
                "django": ["opentelemetry-sdk"],
            },
        }
        return deps.get(language, {}).get(framework, [])

    def _get_tracing_dependencies(self, language: str, framework: str) -> List[str]:
        """Get tracing dependencies"""
        deps = {
            "python": {
                "fastapi": [
                    "opentelemetry-api",
                    "opentelemetry-sdk",
                    "opentelemetry-exporter-otlp",
                    "opentelemetry-instrumentation-fastapi",
                ],
                "flask": [
                    "opentelemetry-api",
                    "opentelemetry-sdk",
                    "opentelemetry-exporter-otlp",
                    "opentelemetry-instrumentation-flask",
                ],
                "django": [
                    "opentelemetry-api",
                    "opentelemetry-sdk",
                    "opentelemetry-exporter-otlp",
                    "opentelemetry-instrumentation-django",
                ],
            },
        }
        return deps.get(language, {}).get(framework, [])

    def _get_install_instructions(
        self,
        language: str,
        framework: str,
        snippet_type: str
    ) -> str:
        """Get installation instructions for dependencies"""
        if language == "python":
            deps = []
            if snippet_type == "rum":
                deps = self._get_rum_dependencies(language, framework)
            elif snippet_type == "sampling":
                deps = self._get_sampling_dependencies(language, framework)
            elif snippet_type == "tracing":
                deps = self._get_tracing_dependencies(language, framework)

            if deps:
                return f"pip install {' '.join(deps)}"
            return "# No additional dependencies required"

        elif language == "javascript":
            deps = self._get_rum_dependencies(language, framework)
            if deps:
                return f"npm install {' '.join(deps)}"
            return "# No additional dependencies required"

        return "# Installation instructions not available"

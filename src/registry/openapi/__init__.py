"""OpenAPI 3.0 / Swagger Auto-Importer for UAOS."""

from src.registry.openapi.openapi_executor import execute_openapi_request
from src.registry.openapi.openapi_parser import parse_openapi_spec

__all__ = ["execute_openapi_request", "parse_openapi_spec"]

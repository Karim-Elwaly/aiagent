"""Unit tests for OpenAPI 3.0 / Swagger Auto-Importer."""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.models import RiskLevel
from src.registry.openapi.openapi_executor import execute_openapi_request
from src.registry.openapi.openapi_parser import parse_openapi_spec

SAMPLE_OPENAPI_SPEC = """
{
  "openapi": "3.0.0",
  "info": {
    "title": "Petstore API",
    "version": "1.0.0"
  },
  "servers": [
    {
      "url": "https://petstore.example.com/v1"
    }
  ],
  "paths": {
    "/pets": {
      "get": {
        "operationId": "listPets",
        "summary": "List all pets",
        "tags": ["pets"],
        "parameters": [
          {
            "name": "limit",
            "in": "query",
            "required": false,
            "schema": {
              "type": "integer"
            }
          }
        ]
      },
      "post": {
        "operationId": "createPet",
        "summary": "Create a new pet",
        "tags": ["pets"],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["name"],
                "properties": {
                  "name": {
                    "type": "string"
                  },
                  "tag": {
                    "type": "string"
                  }
                }
              }
            }
          }
        }
      }
    },
    "/pets/{petId}": {
      "delete": {
        "operationId": "deletePet",
        "summary": "Delete a pet by ID",
        "tags": ["pets"],
        "parameters": [
          {
            "name": "petId",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string"
            }
          }
        ]
      }
    }
  }
}
"""


def test_parse_openapi_spec():
    tools = parse_openapi_spec(SAMPLE_OPENAPI_SPEC, api_prefix="petstore")
    assert len(tools) == 3

    tool_map = {t.name: t for t in tools}

    # 1. listPets
    list_tool = tool_map["petstore_listpets"]
    assert list_tool.risk_level == RiskLevel.LOW
    assert list_tool.source_type == "openapi"
    assert list_tool.server_or_host == "https://petstore.example.com/v1"
    assert "limit" in list_tool.parameters
    assert list_tool.parameters["limit"]["type"] == "integer"
    assert "pets" in list_tool.skills_provided

    # 2. createPet
    create_tool = tool_map["petstore_createpet"]
    assert create_tool.risk_level == RiskLevel.HIGH
    assert "name" in create_tool.parameters
    assert create_tool.parameters["name"]["required"] is True
    assert "tag" in create_tool.parameters

    # 3. deletePet
    delete_tool = tool_map["petstore_deletepet"]
    assert delete_tool.risk_level == RiskLevel.CRITICAL
    assert "petId" in delete_tool.parameters
    assert delete_tool.parameters["petId"]["required"] is True


@pytest.mark.asyncio
async def test_execute_openapi_request():
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.reason_phrase = "OK"
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json = lambda: [{"id": 1, "name": "Fido"}]
    mock_resp.text = '[{"id": 1, "name": "Fido"}]'

    with patch("httpx.AsyncClient.request", return_value=mock_resp) as mock_req:
        output = await execute_openapi_request(
            base_url="https://api.example.com",
            path="/pets/{petId}",
            method="GET",
            parameters_meta={"petId": {"in": "path"}, "limit": {"in": "query"}},
            auth_header_name="Authorization",
            auth_header_value="Bearer test_token",
            tool_name="get_pet",
            call_args={"petId": "42", "limit": 10},
        )

        assert "[HTTP 200 OK]" in output
        assert "Fido" in output

        mock_req.assert_called_once()
        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["params"] == {"limit": 10}
        assert call_kwargs["headers"]["Authorization"] == "Bearer test_token"

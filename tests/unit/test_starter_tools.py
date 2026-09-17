"""
Unit tests for the starter tools:
- code_executor (sandboxed python)
- file_ops (read, write, list, delete)
- web_search (SearXNG client with offline resilience)
"""

import pytest

from src.registry.tools.code_executor import execute_python
from src.registry.tools.file_ops import delete_file, list_directory, read_file, write_file
from src.registry.tools.web_search import web_search


@pytest.mark.asyncio
async def test_code_executor_success():
    code = "print(sum([1, 2, 3, 4, 5]))"
    output = await execute_python(code)
    assert output.strip() == "15"


@pytest.mark.asyncio
async def test_code_executor_syntax_error():
    code = "this is not valid python!!"
    output = await execute_python(code)
    assert "STDERR:" in output
    assert "SyntaxError" in output


@pytest.mark.asyncio
async def test_file_ops_lifecycle(tmp_path):
    test_file = str(tmp_path / "subdir" / "test.txt")
    test_content = "Hello, UAOS!"

    # 1. Write file
    write_res = await write_file(test_file, test_content)
    assert "Successfully wrote" in write_res

    # 2. Read file
    read_res = await read_file(test_file)
    assert read_res == test_content

    # 3. List directory
    list_res = await list_directory(str(tmp_path / "subdir"))
    assert "test.txt" in list_res

    # 4. Delete file
    del_res = await delete_file(test_file)
    assert "Successfully deleted" in del_res

    # 5. Read deleted file
    missing_res = await read_file(test_file)
    assert "Error: File not found" in missing_res


@pytest.mark.asyncio
async def test_web_search_offline_graceful():
    # When SearXNG backend is not running at localhost:8888, it should return a clean message
    res = await web_search("test query")
    assert "Error performing web search" in res or "Cannot search for" in res or "No results" in res


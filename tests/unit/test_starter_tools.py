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


@pytest.mark.asyncio
async def test_get_disk_usage(tmp_path):
    from src.registry.tools.file_ops import get_disk_usage

    # Create dummy files
    sub = tmp_path / "test_folder"
    sub.mkdir()
    (sub / "sample.txt").write_text("content", encoding="utf-8")

    usage_str = await get_disk_usage(str(tmp_path))
    assert "Disk Usage Summary" in usage_str
    assert "Total Storage Capacity" in usage_str
    assert "Free Space Available" in usage_str
    assert "test_folder" in usage_str
    assert "Top-Level Entries and Storage Breakdown" in usage_str
    assert "| Name | Type | Size" in usage_str


@pytest.mark.asyncio
async def test_recursive_directory_listing(tmp_path):
    nested_dir = tmp_path / "parent" / "child"
    nested_dir.mkdir(parents=True)
    (nested_dir / "nested_file.txt").write_text("deep data", encoding="utf-8")

    tree_str = await list_directory(str(tmp_path), recursive=True, max_depth=3)
    assert "Directory Tree" in tree_str
    assert "parent" in tree_str
    assert "child" in tree_str
    assert "nested_file.txt" in tree_str
    assert "items enumerated" in tree_str


@pytest.mark.asyncio
async def test_live_d_drive_and_ai_gpu():
    from pathlib import Path
    exists = Path(r"D:\ai_gpu").exists()
    res_list = await list_directory(r"D:\ai_gpu")
    res_disk = await get_disk_usage(r"D:\ai_gpu")
    assert isinstance(res_list, str) and len(res_list) > 0
    assert isinstance(res_disk, str) and len(res_disk) > 0
    # Both tools must supply host metrics and JSON data even if the specific subfolder is missing
    assert "total_bytes" in res_disk or "Total Storage Capacity" in res_disk
    assert "```json" in res_list or "Directory Tree" in res_list



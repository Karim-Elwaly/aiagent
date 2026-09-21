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
async def test_web_search_returns_usable_string():
    """The search tool must degrade gracefully whether or not a backend is reachable.

    This assertion is deliberately environment-independent: CI may or may not have
    network access, so we verify the contract (always a non-empty string, never an
    unhandled exception) rather than a specific offline message.
    """
    res = await web_search("test query")
    assert isinstance(res, str)
    assert res.strip(), "web_search must never return an empty string"


@pytest.mark.asyncio
async def test_get_disk_usage(tmp_path):
    from src.registry.tools.file_ops import get_disk_usage

    # Create dummy files
    sub = tmp_path / "test_folder"
    sub.mkdir()
    (sub / "sample.txt").write_text("content", encoding="utf-8")

    usage_str = await get_disk_usage(str(tmp_path))
    assert "Host Disk Partition & Directory Storage Breakdown" in usage_str
    assert "Total Capacity" in usage_str
    assert "Free:" in usage_str
    assert "test_folder" in usage_str
    assert "| Name | Type | Size" in usage_str
    # Machine-readable metrics block for downstream verification
    assert "```json" in usage_str
    assert "total_bytes" in usage_str


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
async def test_missing_path_falls_back_to_host_drive(tmp_path):
    """A non-existent target must still yield host metrics, not an unhandled error.

    Uses a path guaranteed not to exist rather than a machine-specific directory,
    so the test is portable across developer machines and CI.
    """
    from src.registry.tools.file_ops import get_disk_usage

    missing = str(tmp_path / "definitely_not_present_dir")

    res_list = await list_directory(missing)
    res_disk = await get_disk_usage(missing)

    assert isinstance(res_list, str) and res_list.strip()
    assert isinstance(res_disk, str) and res_disk.strip()
    # Host-level metrics are reported even though the subfolder is missing
    assert "total_bytes" in res_disk or "Total Capacity" in res_disk



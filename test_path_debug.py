from src.core.path_utils import resolve_target_path
from pathlib import Path

test_cases = [
    r"D:\ ",
    r": D:\",
    r"D:\",
    r"D:",
    r"D",
    r"get the dir size : D:\",
    r"D:/",
]

for tc in test_cases:
    res = resolve_target_path(tc)
    print(f"INPUT: {repr(tc)} -> RESULT: {repr(str(res))} (exists={res.exists()}, is_dir={res.is_dir()})")

import os
import shutil
import stat
import sys

target = r"\\?\D:\projects\aiagent\frontend\aiagent"

def remove_readonly(func, path, excinfo):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception as e:
        pass

if os.path.exists(target):
    print(f"[*] Removing deep nested directory: {target}...")
    try:
        shutil.rmtree(target, onerror=remove_readonly)
        print("[OK] Successfully cleaned up nested directory!")
    except Exception as e:
        print(f"[!] Removal encountered issue: {e}")
else:
    print("[OK] Deep nested directory does not exist or already removed.")

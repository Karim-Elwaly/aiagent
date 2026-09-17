import socket
import asyncio
from src.registry.tools.file_ops import list_directory, get_disk_usage
from src.registry.tools.system_commands import execute_command

for port in [8000, 8001, 8002, 8080, 8233, 7233]:
    s = socket.socket()
    s.settimeout(0.5)
    res = s.connect_ex(("127.0.0.1", port))
    s.close()
    print(f"Port {port}: {'OPEN' if res == 0 else 'CLOSED'}")

async def test_tools():
    print("\n--- Testing get_disk_usage('D:\\') ---")
    usage = await get_disk_usage("D:\\")
    print(usage[:1000])

    print("\n--- Testing list_directory('D:\\', recursive=True, max_depth=2, max_items=25) ---")
    tree = await list_directory("D:\\", recursive=True, max_depth=2, max_items=25)
    print(tree[:1000])

    print("\n--- Testing execute_command('fsutil volume diskfree D:') ---")
    cmd_res = await execute_command("fsutil volume diskfree D:")
    print(cmd_res[:500])

asyncio.run(test_tools())

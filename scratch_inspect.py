import os
import sys

target = r"D:\Security-logs-test\attack-cases-benchmark\case-1-apt-enterprise-intrusion\CASE_REPORT.md"
if os.path.exists(target):
    with open(target, 'r', encoding='utf-8', errors='ignore') as f:
        print(f.read()[:3000])
else:
    print(f"File not found: {target}")
    parent = os.path.dirname(target)
    if os.path.exists(parent):
        print("Parent dir contents:", os.listdir(parent))

import os

case_dir = r"D:\Security-logs-test\attack-cases-benchmark\case-1-apt-enterprise-intrusion"
print("Files in case_dir:", os.listdir(case_dir))

report_path = os.path.join(case_dir, "CASE_REPORT.md")
if os.path.exists(report_path):
    with open(report_path, "r", encoding="utf-8", errors="replace") as f:
        print("=== CASE_REPORT.md ===")
        print(f.read()[:3000])

logs_dir = os.path.join(case_dir, "raw-logs")
if os.path.exists(logs_dir):
    print("\nFiles in raw-logs:", os.listdir(logs_dir))

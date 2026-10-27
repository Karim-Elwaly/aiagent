import os
import pathlib
import json

appdata = os.environ.get("LOCALAPPDATA")
prof_name = "fleet-manages-end-end-define-recruitment-w"
hermes_prof_dir = pathlib.Path(appdata) / "hermes" / "profiles" / prof_name

print("=== Hermes Profile Dir ===")
print("Path:", hermes_prof_dir)
print("Exists:", hermes_prof_dir.exists())

cfg = hermes_prof_dir / "config.yaml"
if cfg.exists():
    print("\n--- config.yaml ---")
    print(cfg.read_text(encoding="utf-8"))

skills_dir = hermes_prof_dir / "skills"
print("\n--- Profile Skills Dir:", skills_dir, "---")
if skills_dir.exists():
    for item in skills_dir.iterdir():
        print("Skill item:", item.name)
        if item.is_dir():
            for sub in item.iterdir():
                print("   ", sub.name)

ext_skills_dir = pathlib.Path("d:/projects/aiagent/data/hermes/skills") / prof_name
print("\n--- External Skills Dir:", ext_skills_dir, "---")
if ext_skills_dir.exists():
    for item in ext_skills_dir.iterdir():
        print("Ext skill item:", item.name)
        if item.is_dir():
            for sub in item.iterdir():
                print("   ", sub.name)

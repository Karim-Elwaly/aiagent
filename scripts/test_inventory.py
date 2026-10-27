import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.core.config import get_settings
from src.hermes.profiles import HermesProfiles

def main():
    settings = get_settings()
    profiles = HermesProfiles(settings)
    skills = profiles.list_available_library_skills()
    print(f"Discovered {len(skills)} library skills from Hermes:")
    for name in sorted(skills.keys())[:15]:
        desc = skills[name].get("description", "")[:60]
        print(f"  - {name}: {desc}")
    if len(skills) > 15:
        print(f"  ... and {len(skills) - 15} more.")

    # Check ensure_fleet_unit on one specialist
    unit_name = "fleet-manages-end-end-define-recruitment-w"
    print(f"\nTesting ensure_fleet_unit on '{unit_name}'...")
    info = profiles.ensure_fleet_unit(
        profile_name=unit_name,
        unit_name="Define Recruitment Workflow",
        role="PLANNER",
        scope="Architect the end-to-end recruitment process",
        skills=["general_reasoning"],
        tools=["web", "browser", "file"],
        arena_name="Talent Acquisition (TA)",
        input_contract="None",
        output_contract="Verified workflow payload",
    )
    pdir = profiles.home / "profiles" / unit_name
    skills_dir = pdir / "skills"
    p_skills = list(skills_dir.iterdir()) if skills_dir.is_dir() else []
    print(f"Specialist '{unit_name}' now has {len(p_skills)} skills installed in {skills_dir}:")
    for s in sorted([p.name for p in p_skills])[:10]:
        print(f"  - {s}")
    if len(p_skills) > 10:
        print(f"  ... and {len(p_skills) - 10} more.")

if __name__ == "__main__":
    main()

@echo off
echo ========================================================
echo Running UAOS Hermes Upgrade Unit Test Suite
echo ========================================================
pytest tests/unit/test_phase0_foundations.py ^
       tests/unit/test_phase1_tool_calling_and_reflection.py ^
       tests/unit/test_phase2_python_session_and_memory.py ^
       tests/unit/test_phase3_skills_and_browser.py ^
       tests/unit/test_distilled_skills_and_memory_api.py ^
       tests/unit/test_phase3b_embeddings.py ^
       tests/unit/test_eval_runner.py -v
echo ========================================================
pause

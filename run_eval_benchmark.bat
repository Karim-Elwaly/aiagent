@echo off
echo ========================================================
echo Running UAOS Evaluation Benchmark Suite (40 cases)
echo ========================================================
python -m tests.eval.runner --mode auto --output data/eval/hermes_benchmark_results.json
echo ========================================================
pause

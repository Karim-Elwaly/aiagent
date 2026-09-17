#!/usr/bin/env bash
# UAOS One-Command Starter for Linux/macOS

if [ -f ".venv/bin/python" ]; then
    .venv/bin/python run.py
else
    python3 run.py
fi

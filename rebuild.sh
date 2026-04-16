#!/bin/bash
pkill -f "Eye.app" 2>/dev/null
.venv/bin/python setup.py py2app 2>&1 | tail -3
open dist/Eye.app 

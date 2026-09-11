#!/bin/sh
PRIVACY_HOOK_SCANNER=tools/omama/privacy-hook/scan_staged.py
export PRIVACY_HOOK_SCANNER
exec sh .githooks/privacy-pre-commit

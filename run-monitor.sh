#!/bin/sh

SCRIPT_PATH=$(dirname $(readlink -f "$0"))
cd "$SCRIPT_PATH" && ./monitor/unifi-monitor.py unifi.m default 30 "$@"

#!/bin/sh

SCRIPT_PATH=$(dirname $(readlink -f "$0"))
cd "$SCRIPT_PATH" && ./manager/unifi-manager.py unifi.m default "$@"

#!/bin/sh
# Coordinator acquisition only; Pekit executes workers in offline namespaces.
set -eu
exec python3 "$(dirname "$0")/prepare.py"

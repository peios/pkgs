#!/usr/bin/sh

hook_log_init() { HOOK_LOG_COMPONENT=$1; }
log_ok()   { printf 'OK %s: %s\n' "$HOOK_LOG_COMPONENT" "$*"; }
log_skip() { printf 'SKIP %s: %s\n' "$HOOK_LOG_COMPONENT" "$*"; }
log_warn() { printf 'WARN %s: %s\n' "$HOOK_LOG_COMPONENT" "$*" >&2; }
log_fail() { printf 'FAIL %s: %s\n' "$HOOK_LOG_COMPONENT" "$*" >&2; }

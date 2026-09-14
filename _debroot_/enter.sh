#!/bin/sh
# Install dependencies without any job/source mounts, then export the root.
# Pekit runs the target in its own offline namespace after this has exited.
set -eu
: "${PEKIT_SANDBOX_ROOT:?Pekit must supply a private root destination}"
# Reuse only dependency roots prepared in this job; workers see them read-only.
fingerprint=$(printf '%s' "${PEKIT_DEPENDENCIES:-}" | sha256sum | cut -d' ' -f1)
cache="$PEKIT_JOB_STATE/debian-roots/$fingerprint"
record="$PEKIT_JOB_STATE/dependencies/$PEKIT_COMMAND-$PEKIT_TARGET"
if [ -d "$cache/root" ]; then
  cp -a "$cache/root" "$PEKIT_SANDBOX_ROOT"
  mkdir -p "$record"
  cp "$cache/installed.tsv" "$cache/base-image.txt" "$record/"
  exit 0
fi
container=
cleanup() { [ -z "$container" ] || docker rm -f "$container" >/dev/null; }
trap cleanup EXIT INT TERM
container=$(docker create --network bridge -e PEKIT_DEPENDENCIES="${PEKIT_DEPENDENCIES:-}" debian:trixie sh -euc '
  apt-get update -q
  # Preserve constraints as assertions against the installed package version.
  # Wildcards track the current archive without requiring manual pins.
  printf "%s\n" "$PEKIT_DEPENDENCIES" | while read -r name constraint; do
    [ -n "$name" ] || continue
    case "$name" in *[!a-z0-9+.-]*|-*) echo "invalid apt package: $name" >&2; exit 1;; esac
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends "$name"
    if [ -n "$constraint" ] && [ "$constraint" != "*" ]; then
      actual=$(dpkg-query -W -f="\${Version}" "$name")
      op=${constraint%% *}; required=${constraint#* }
      case "$op" in "=") op=eq;; ">=") op=ge;; ">") op=gt;; "<=") op=le;; "<") op=lt;; *) echo "unsupported apt constraint: $constraint" >&2; exit 1;; esac
      dpkg --compare-versions "$actual" "$op" "$required" || { echo "$name $actual does not satisfy $constraint" >&2; exit 1; }
    fi
  done
  dpkg-query -W -f="\${Package}\t\${Version}\n" > /tmp/dependencies.tsv
  printf "peibuild:x:1000:1000:Package builder:/tmp:/bin/sh\n" >> /etc/passwd
  printf "peibuild:x:1000:\n" >> /etc/group
')
docker start -a "$container"
[ "$(docker inspect -f '{{.State.ExitCode}}' "$container")" = 0 ]
record="$PEKIT_JOB_STATE/dependencies/$PEKIT_COMMAND-$PEKIT_TARGET"
mkdir -p "$record"
docker cp "$container:/tmp/dependencies.tsv" "$record/installed.tsv"
docker inspect -f '{{.Image}}' "$container" > "$record/base-image.txt"
# Export strips image volumes; download caches and the Docker socket remain
# coordinator-side. The temporary archive avoids swallowing pipeline failure.
archive=$(mktemp)
trap 'rm -f "$archive"; cleanup' EXIT INT TERM
docker export "$container" -o "$archive"
mkdir -p "$PEKIT_SANDBOX_ROOT"
tar --no-same-owner -xf "$archive" -C "$PEKIT_SANDBOX_ROOT"

mkdir -p "$cache"
cp -a "$PEKIT_SANDBOX_ROOT" "$cache/root"
cp "$record/installed.tsv" "$record/base-image.txt" "$cache/"

#!/bin/sh
set -eu

mp_test_root=$(mktemp -d "${TMPDIR:-/tmp}/medium-packages.XXXXXX")
trap 'rm -rf "$mp_test_root"' EXIT INT TERM
mkdir -p "$mp_test_root/bin"
cat > "$mp_test_root/bin/peipkg" <<'STUB'
#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$MP_CALLS"
[ "$1" = --root ]
r=$2; shift 2
verb=$1; shift
case "$verb" in
    repo)
        case "$1" in
            add) [ -f "$r/repo-config" ] || exit 1 ;;
            remove)
                rm -f "$r/repo-config"
                [ "${MP_FAIL:-}" != repo-remove ] || exit 1
                ;;
            *) exit 2 ;;
        esac
        ;;
    list)
        [ "${MP_FAIL:-}" != list ] || exit 1
        if [ -s "$r/packages" ]; then cat "$r/packages"; else printf '%s\n' 'no packages are installed'; fi
        ;;
    uninstall)
        [ "$1" = --yes ]; shift
        case "$r:${MP_FAIL:-}" in */boot/initramfs:initramfs) exit 1 ;; esac
        while read -r name rest; do
            case " $* " in *" $name "*) ;; *) printf '%s %s\n' "$name" "$rest" ;; esac
        done < "$r/packages" > "$r/packages.new"
        mv "$r/packages.new" "$r/packages"
        ;;
    install)
        [ "${MP_FAIL:-}" != install ] || exit 1
        while read -r name rest; do
            [ "$name" = dev.peios.disk-boot ] || printf '%s %s\n' "$name" "$rest"
        done < "$r/packages" > "$r/packages.new"
        printf '%s\n' 'dev.peios.disk-boot 1 noarch' >> "$r/packages.new"
        mv "$r/packages.new" "$r/packages"
        ;;
    *) exit 2 ;;
esac
STUB
mkexec "$mp_test_root/bin/peipkg"
PATH="$mp_test_root/bin:$PATH"
MP_CALLS="$mp_test_root/calls"
MP_FAIL=''
export PATH MP_CALLS MP_FAIL
PEIOS_INSTALL_LIBRARY_ONLY=1
export PEIOS_INSTALL_LIBRARY_ONLY
. ./src/peios-install.sh

new_target() {
    rm -rf "$mp_test_root/target"
    mkdir -p "$mp_test_root/target/lcl/policy" "$mp_test_root/target/boot/initramfs"
    printf '%s\n' 'dev.peios.live-boot 1 noarch' 'dev.peios.dwed 1 noarch' \
        'dev.example.live-only 1 noarch' 'dev.example.keep 1 noarch' > "$mp_test_root/target/packages"
    printf '%s\n' 'dev.peios.live-boot-irf 1 noarch' 'dev.example.keep-irf 1 noarch' > "$mp_test_root/target/boot/initramfs/packages"
    printf '%s\n' peios-medium-packages-v1 'root dev.peios.live-boot' \
        'initramfs dev.peios.live-boot-irf' 'root dev.peios.dwed' \
        'root dev.example.live-only' > "$mp_test_root/target/lcl/policy/medium-only-packages"
    : > "$mp_test_root/target/repo-config"
    : > "$MP_CALLS"
    MP_FAIL=''
}
has_package() {
    while read -r hp_name hp_rest; do [ "$hp_name" != "$2" ] || return 0; done < "$1/packages"
    return 1
}

new_target
finish_medium_packages "$mp_test_root/target"
[ ! -e "$mp_test_root/target/lcl/policy/medium-only-packages" ]
has_package "$mp_test_root/target" dev.example.keep
has_package "$mp_test_root/target" dev.peios.disk-boot
has_package "$mp_test_root/target/boot/initramfs" dev.example.keep-irf
for name in dev.peios.live-boot dev.peios.dwed dev.example.live-only; do
    if has_package "$mp_test_root/target" "$name"; then echo "kept medium-only $name" >&2; exit 1; fi
done

for failure in initramfs install repo-remove list; do
    new_target
    MP_FAIL=$failure
    if finish_medium_packages "$mp_test_root/target"; then echo "ignored $failure" >&2; exit 1; fi
    [ -f "$mp_test_root/target/lcl/policy/medium-only-packages" ]
    if [ "$failure" = repo-remove ]; then
        [ ! -e "$mp_test_root/target/repo-config" ]
        [ "$(cat "$mp_test_root/target/lcl/policy/medium-only-packages")" = peios-medium-packages-complete-v1 ]
    else
        [ -f "$mp_test_root/target/repo-config" ]
        case "$(cat "$MP_CALLS")" in *"repo remove peios-medium"*) echo 'removed repository needed by retry' >&2; exit 1 ;; esac
    fi
    if [ "$failure" = list ]; then
        has_package "$mp_test_root/target" dev.peios.live-boot
        has_package "$mp_test_root/target/boot/initramfs" dev.peios.live-boot-irf
    fi
    MP_FAIL=''
    : > "$MP_CALLS"
    finish_medium_packages "$mp_test_root/target"
    [ ! -e "$mp_test_root/target/lcl/policy/medium-only-packages" ]
    if [ "$failure" = repo-remove ]; then
        [ "$(cat "$MP_CALLS")" = "--root $mp_test_root/target repo remove peios-medium" ]
    fi
done

# A completed marker can survive successful repository cleanup if its own
# deletion fails. Repeating cleanup must not recreate trust or install again.
new_target
printf '%s\n' peios-medium-packages-complete-v1 > "$mp_test_root/target/lcl/policy/medium-only-packages"
rm "$mp_test_root/target/repo-config"
finish_medium_packages "$mp_test_root/target"
[ "$(cat "$MP_CALLS")" = "--root $mp_test_root/target repo remove peios-medium" ]
[ ! -e "$mp_test_root/target/lcl/policy/medium-only-packages" ]
has_package "$mp_test_root/target" dev.peios.live-boot


new_target
rm "$mp_test_root/target/lcl/policy/medium-only-packages"
MP_FAIL=initramfs
if finish_medium_packages "$mp_test_root/target"; then exit 1; fi
[ -f "$mp_test_root/target/lcl/policy/medium-only-packages" ]
MP_FAIL=''
finish_medium_packages "$mp_test_root/target"
has_package "$mp_test_root/target" dev.peios.dwed
has_package "$mp_test_root/target" dev.example.live-only

for invalid in 'elsewhere dev.example.x' 'root --cascade' 'root ../x' 'root x extra'; do
    new_target
    printf '%s\n' peios-medium-packages-v1 "$invalid" > "$mp_test_root/target/lcl/policy/medium-only-packages"
    if finish_medium_packages "$mp_test_root/target"; then echo "accepted $invalid" >&2; exit 1; fi
    [ ! -s "$MP_CALLS" ]
done
new_target
printf '%s\n' peios-medium-packages-v2 > "$mp_test_root/target/lcl/policy/medium-only-packages"
if finish_medium_packages "$mp_test_root/target"; then exit 1; fi
[ ! -s "$MP_CALLS" ]
new_target
printf '%s\n' 'root dev.peios.dwed' >> "$mp_test_root/target/lcl/policy/medium-only-packages"
if finish_medium_packages "$mp_test_root/target"; then exit 1; fi
[ ! -s "$MP_CALLS" ]

for suffix in '' '\n\n' '\nroot x\n'; do
    new_target
    printf 'peios-medium-packages-complete-v1%b' "$suffix" > "$mp_test_root/target/lcl/policy/medium-only-packages"
    if finish_medium_packages "$mp_test_root/target"; then echo 'accepted malformed completion' >&2; exit 1; fi
    [ ! -s "$MP_CALLS" ]
done

printf '%s\n' 'medium-only package tests: PASS'

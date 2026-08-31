#!/usr/bin/sh
# peios-install — install the running live system onto a disk.
#
# Two forms. Given two partitions it writes a bootable Peios onto them; given a
# whole disk and --whole-disk it partitions the disk first, using `part`.
#
# What it does, in order:
#
#   0. partition         --whole-disk only: a fresh GPT, a 512 MiB ESP and a
#                        root filling the rest
#   1. format the ESP    FAT32, because UEFI requires it
#   2. format the root   ext4, with a security descriptor stamped at format
#                        time so the filesystem carries its own access policy
#   3. copy the tree     cp -ax, preserving owner/DACL/SACL and stopping at
#                        filesystem boundaries
#   4. swap the boot     replace the live-boot packages with the disk-boot ones
#                        IN THE TARGET, from the repository on the medium
#   5. write the cmdline the target's template plus root=UUID=<the new root>
#   6. rebuild the cpio  mkirf, so the target's initramfs carries the disk hook
#   7. build the UKI     kernel + the NEW initramfs + cmdline, onto the ESP
#
# There is no bootloader and no NVRAM entry: the UKI goes to the EFI
# removable-media fallback path, which firmware boots on its own.
set -eu

progname=peios-install

# 512 MiB matches what dist/Makefile's sgdisk wrote when the test disk was
# partitioned on the host, so a --whole-disk install produces a byte-identical
# layout to the one every earlier install was verified against. It is also far
# more than a UKI needs (~45 MiB), leaving room for a second kernel.
#
# Defined before usage(), which interpolates it: under `set -eu` an unset
# variable in that heredoc would turn "here is how to use me" into an abort.
ESP_SIZE=512M

usage() {
    cat >&2 <<EOF
usage: $progname --yes ESP_PARTITION ROOT_PARTITION
       $progname --yes --whole-disk DISK [--force]

Install the running system onto a disk. EVERYTHING NAMED IS ERASED. --yes is
required; there is no interactive confirmation.

  ESP_PARTITION   EFI system partition, formatted FAT32 (e.g. /dev/vdb1)
  ROOT_PARTITION  root filesystem, formatted ext4      (e.g. /dev/vdb2)

  --whole-disk    partition DISK first: a fresh GPT, a ${ESP_SIZE} ESP, and a
                  root filling the rest. THE WHOLE DISK IS ERASED.
  --force         also replace a partition table part did not create (an MBR
                  disk, a damaged GPT, a bare filesystem). Without it, such a
                  disk stops the install rather than being overwritten.
EOF
    exit 2
}

die() {
    echo "$progname: $*" >&2
    exit 1
}

# Is NAME a block device the kernel knows about?
#
# Asks /proc/partitions rather than testing `[ -b /dev/NAME ]`, because the
# obvious test does not work on Peios. `[ -b ]` stats the node, and stat on a
# device node is refused even to a caller that can read and write the device
# perfectly well — so `[ -b ]` reports "not a block device" for a disk that is
# plainly present in /proc/partitions (PEI-196).
#
# Why the stat is refused is still open. It is NOT the access mask, though an
# earlier revision of this comment claimed so: `sd show` prints masks in short
# form, and the `f` on those descriptors is the composite FILE_ALL
# (0x001F01FF) — full access — not hex 0xF. That misreading became a confident
# root cause in four places before it was caught.
#
# The failure is worse than an error, because `[ -b ]` cannot distinguish
# "absent" from "denied": both are false. An installer that says "/dev/vdb is
# not a block device" about an attached 8G disk sends the operator looking for
# a hardware problem.
#
# /proc/partitions is the kernel's own list, needs no access to the node, and
# needs no tool Peios does not ship. `part` reached the same conclusion from
# the other direction and asks sysfs; this is the same idea with one fewer
# assumption about which paths are readable.
is_block_device() {
    name=${1#/dev/}
    # An empty name would match the blank line /proc/partitions carries under
    # its header, so an unset variable would be reported as a valid device and
    # the installer would go on to format it. A name with a slash left in it is
    # not a device in /dev either.
    [ -n "$name" ] || return 1
    case "$name" in */*) return 1 ;; esac
    while read -r _major _minor _blocks devname; do
        [ "$devname" = "$name" ] && return 0
    done < /proc/partitions
    return 1
}

# The security descriptor stamped on the new root at format time. Byte-for-byte
# what the live system's root carries: SYSTEM and BUILTIN\Administrators
# GenericAll, Everyone read+execute, every ACE inheritable. Deliberately the
# same answer rather than a second one — an installed system should not
# silently have a different access policy from the live system it was copied
# from.
#
# Everyone needs the execute bit, not just read: execute is traverse
# (KACS_FILE_TRAVERSE == KACS_FILE_EXECUTE), and an explicit chdir does not get
# the SeChangeNotifyPrivilege traverse bypass, so a service that is not SYSTEM
# cannot enter its own working directory without it (PEI-546). SYSTEM and
# Administrators keep GenericAll rather than read/write/execute because GA
# carries WRITE_DAC, WRITE_OWNER and DELETE, which re-stamping descriptors
# needs.
#
# CREATOR OWNER, inherit-only, gives whoever creates an object full control of
# it. Without it a non-SYSTEM principal can create a file it cannot read back:
# the inherited SYSTEM and Administrators ACEs are a non-empty DACL, and the
# token's default DACL is only consulted when inheritance yields nothing.
#
# The two other copies that must agree are the live root's mount hook
# (live-boot's mount-root.sh) and peinit's PHASE1_SEED_SDDL. NOT seed-sd's
# built-in default, which stays narrower on purpose: that one also stamps /dev,
# where every ACE is inherited by the next hot-plugged block device.
#
# Note the limit this inherits along with it: one inheritable ACL is the whole
# tree's policy. It cannot express "readable system tree, private home
# directories"; that needs per-subtree descriptors, which nothing produces yet.
ROOT_SDDL='O:SYG:SYD:(A;OICI;GA;;;SY)(A;OICI;GA;;;BA)(A;OICI;GRGX;;;WD)(A;OICIIO;GA;;;S-1-3-0)'

# The repository on the installation medium, and the package swap it exists
# for. A live image cannot carry disk-boot: live-boot-irf conflicts with
# disk-boot-irf, and PSD-009 §4.2.5(2) scopes conflicts to a root, so no single
# initramfs root can hold both hooks. The packages the target needs therefore
# ride on the medium instead of in the image, and this is where they come from.
MEDIUM_REPO=peios-medium

# Where the target's cmdline template comes from — read from the TARGET, after
# the swap, not from the live system. The template belongs to the disk-boot
# version being installed, and taking it from the live image would mean
# installing one version's hook and another version's kernel arguments.
CMDLINE_TEMPLATE_REL=usr/share/disk-boot/cmdline

WORK=/run/peios-install
ESP_MNT="$WORK/esp"
ROOT_MNT="$WORK/root"

confirmed=no
whole_disk=no
force=

while [ $# -gt 0 ]; do
    case "$1" in
        --yes)        confirmed=yes ;;
        --whole-disk) whole_disk=yes ;;
        --force)      force=--force ;;
        -h|--help)    usage ;;
        -*)           die "unknown option $1" ;;
        *)            break ;;
    esac
    shift
done
[ "$confirmed" = yes ] || usage

if [ "$whole_disk" = yes ]; then
    [ $# -eq 1 ] || usage
    disk=$1
else
    [ $# -eq 2 ] || usage
    [ -z "$force" ] || die "--force only means anything with --whole-disk"
    esp_part=$1
    root_part=$2
fi

# --- partition ----------------------------------------------------------------
# Only for --whole-disk. `part` does its own refusing — it will not touch a
# partition rather than a disk, will not touch a disk with anything mounted on
# it, and will not replace a table it did not create unless --force says so —
# so this does not re-implement those checks, it just does not swallow them.
#
# `part` exits 3 specifically for a refusal, as opposed to 1 for a failure.
# The distinction is worth surfacing: "this disk is not what you said it was"
# deserves a different message from "partitioning broke".
if [ "$whole_disk" = yes ]; then
    is_block_device "$disk" || die "$disk is not a block device the kernel knows about"

    echo "$progname: partitioning $disk (everything on it is erased)"
    if ! part create "$disk" --yes $force; then
        rc=$?
        [ "$rc" = 3 ] && die "$disk carries a partition table part will not replace; \
pass --force if you mean to destroy it"
        die "could not write a partition table to $disk"
    fi
    part add "$disk" --size "$ESP_SIZE" --type esp   --name "EFI system partition" --yes \
        || die "could not create the ESP on $disk"
    part add "$disk" --size max         --type linux --name "Peios root"           --yes \
        || die "could not create the root partition on $disk"

    # Name the new partitions. The suffix is not universal — sd*/vd* number
    # directly (vdb1) while nvme*/mmcblk* interpose a `p` (nvme0n1p1) — so probe
    # for the node the kernel actually created rather than assuming either.
    # These exist only because `part` issued BLKRRPART and /dev is devtmpfs, so
    # the kernel's own device model materialised them; no udev is involved,
    # which matters because Peios ships none.
    if   is_block_device "${disk}1"  && is_block_device "${disk}2";  then part_prefix=""
    elif is_block_device "${disk}p1" && is_block_device "${disk}p2"; then part_prefix="p"
    else
        die "partitioned $disk but ${disk}1 and ${disk}p1 are both absent; \
the kernel did not pick up the new table"
    fi
    esp_part="${disk}${part_prefix}1"
    root_part="${disk}${part_prefix}2"
    echo "$progname: created $esp_part (ESP) and $root_part (root)"
fi

# --- checks ------------------------------------------------------------------
# Pure shell, and deliberately so: Peios ships no grep. peiosutils is a
# coreutils fork, and grep has never been part of coreutils — so the `grep -q`
# this replaces resolved to nothing, sh exited 127, and the `if` was simply
# false. The guard below read as if it worked and had in fact never once
# fired. /proc/mounts is the authority either way; reading it directly needs no
# package to be present.
is_mounted_device() {
    while read -r source _target _rest; do
        [ "$source" = "$1" ] && return 0
    done < /proc/mounts
    return 1
}

for dev in "$esp_part" "$root_part"; do
    is_block_device "$dev" || die "$dev is not a block device the kernel knows about"
    # A mounted target would be destroyed under a running filesystem. This also
    # catches the obvious disaster of naming the partition you booted from.
    if is_mounted_device "$dev"; then
        die "$dev is mounted; refusing to format it"
    fi
done
[ "$esp_part" != "$root_part" ] || die "the ESP and root partitions must differ"

# Everything the swap needs, checked before anything is destroyed. Each of
# these fails late and expensively otherwise: after the disk is formatted and
# several minutes of copying, with a half-installed system on it.
command -v peipkg >/dev/null 2>&1 \
    || die "peipkg is not installed; the installer needs it to swap the boot packages"
# The pipeline's subshell reports the answer through its exit status; a
# variable set inside it would not survive back to here.
if ! peipkg repo list 2>/dev/null | {
    while read -r name _rest; do
        [ "$name" = "$MEDIUM_REPO" ] && exit 0
    done
    exit 1
}; then
    die "no repository named $MEDIUM_REPO is configured; \
this image cannot install itself without the packages on its medium"
fi

# The kernel to bundle into the UKI. Glob rather than hardcode: the release is
# in both the directory and the filename, and an image may carry more than one.
kernel=
for candidate in /usr/lib/modules/*/vmlinuz-*; do
    [ -f "$candidate" ] || continue
    [ -z "$kernel" ] || die "more than one kernel found; refusing to guess"
    kernel=$candidate
done
[ -n "$kernel" ] || die "no kernel found under /usr/lib/modules/*/vmlinuz-*"

# A pre-flight only: the archive that ends up on the target is rebuilt from
# the target's own initramfs root after the package swap. This checks the live
# system is the shape the copy below assumes.
[ -r /system/boot/initramfs.cpio.zst ] || die "missing /system/boot/initramfs.cpio.zst"

echo "$progname: kernel     $kernel"
echo "$progname: ESP        $esp_part"
echo "$progname: root       $root_part"

# --- retire the first-account provisioning service ----------------------------
# lpsd-first-account is a oneshot that creates the development account by
# running `lps add` at boot. It is a PROVISIONING hook, and it is written for
# exactly one situation, which its own script states: a live image, where the
# root is tmpfs, so every boot starts from an empty store.
#
# An installed system is the other situation. The account itself lives in
# lpsd's store at /var/state/lpsd/principals, which is ordinary content on the
# root filesystem and is copied across with everything else — so the installed
# machine already has the account. Re-running a provisioner against a store
# that is already populated is not a no-op: the script carries no idempotence
# guard, so `lps add` fails on the existing name and the service crashes on
# every boot. Once the installer grows a "choose a password" step, it would be
# worse than noisy — a provisioner that reasserts the image's credential would
# undo the operator's choice at the next reboot.
#
# So the installer retires it. The script and its service exist to get the
# FIRST account onto a machine that has none; the target has one already.
#
# Removed from the LIVE registry rather than from the target, because the hive
# is a live SQLite database under /var/state/loregd and the only thing that can
# safely edit it is the registryd currently serving it. Deleting the key now
# means the copy below never carries it. The alternative — an autorun queued
# onto the target to delete the key at first boot — would defer the removal to
# a boot that might not reach Phase 1.5, and the .reg batch format has no
# delete operation to express it with in any case.
#
# Mutating the system we are running on is safe here and stays safe:
#   - the live root is a tmpfs overlay, discarded at reboot
#   - the service is a boot-triggered oneshot that has already run by the time
#     anyone is at a console to type this, so removing its definition changes
#     nothing about the session in progress
#   - installing FROM an installed system finds nothing to delete, because that
#     system was installed by this same step
#
# NOTE what this does NOT do: the account comes across, and so does its
# password, which is the one written into the image and therefore public. Until
# the installer can prompt for a new one, an installed system should be treated
# as carrying a known credential.
#
# Verified rather than assumed, and fatal — an installer that silently half
# does its job is worse than one that stops and says why. This runs before
# either partition is formatted, so stopping here costs nothing.
FIRST_ACCOUNT_KEY='Machine\System\Services\lpsd-first-account'
if reg info "$FIRST_ACCOUNT_KEY" >/dev/null 2>&1; then
    echo "$progname: retiring the first-account provisioning service"
    reg del "$FIRST_ACCOUNT_KEY" --yes >/dev/null \
        || die "could not remove $FIRST_ACCOUNT_KEY"
    if reg info "$FIRST_ACCOUNT_KEY" >/dev/null 2>&1; then
        die "$FIRST_ACCOUNT_KEY is still present after deleting it; refusing to install"
    fi
else
    echo "$progname: no first-account provisioning service to retire"
fi

# --- format ------------------------------------------------------------------
echo "$progname: formatting $esp_part as FAT32"
mkfs.vfat -F 32 -n PEIOSESP "$esp_part"

# -E root_sddl= is the Peios extension: it writes the descriptor above to the
# root inode's security.peios.sd at format time, so the filesystem is
# administrable from the instant it exists and mounts under deny-missing with
# no mount-level template. Everything created inside it afterwards derives its
# own descriptor from that one by ordinary inheritance.
#
# -F because this must not prompt. mke2fs stops to ask before overwriting an
# existing filesystem, which is right at a terminal and wrong here: --yes is
# already the confirmation, both partitions were named explicitly, and the
# mounted-device check above is the guard that actually matters. Without it a
# second run — after a failure, or simply reinstalling — hangs on a question
# nobody is there to answer.
echo "$progname: formatting $root_part as ext4, stamping the root descriptor"
mke2fs -qF -t ext4 -L peios-root -E "root_sddl=$ROOT_SDDL" "$root_part"

# --- mount -------------------------------------------------------------------
# Under /run, which is a tmpfs: the copy below stops at filesystem boundaries,
# so mounting here means the mountpoints are never created on the target.
mkdir -p "$ESP_MNT" "$ROOT_MNT"
cleanup() {
    umount "$ESP_MNT" 2>/dev/null || true
    umount "$ROOT_MNT" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# deny-missing on the target, matching how it will be mounted at boot: the
# descriptor is already on it, so nothing needs synthesising.
mount -o policy=deny-missing "$root_part" "$ROOT_MNT"
# FAT holds no descriptors and never can, so its access policy has to come from
# the mount. Ephemeral: synthesise in memory, write nothing back.
mount -o policy=synth-ephemeral --synth-sddl "$ROOT_SDDL" "$esp_part" "$ESP_MNT"

# --- copy --------------------------------------------------------------------
# Copied entry by entry rather than as one `cp -a /. target/`, for two reasons.
#
# The first is that cp refuses the whole-root form outright — "cannot copy a
# directory into itself" — because the destination is necessarily somewhere
# under /. It cannot know that -x would have stopped before reaching it.
#
# The second is that -x alone would not do the right thing anyway. It skips
# subdirectories that sit on a different filesystem than the STARTING POINT, so
# naming a mountpoint as the source makes that mount the starting point and cp
# happily copies the whole of /proc. Mountpoints have to be excluded here, at
# the top level, where we can still tell them apart.
#
# What each mountpoint needs on the target is the empty directory, not the
# contents: prelude mount-moves /proc, /sys and /dev into the new root, and
# stratafs-base-topo mounts /bin, /etc, /lib and friends over theirs. The
# content behind those views lives in /usr and /lcl, which are ordinary
# directories on the root filesystem and are copied in full.
#
# This is also what keeps the copy away from its own destination: the target is
# mounted under /run, which is a tmpfs and therefore skipped as a mountpoint.
#
# -a and nothing else: owner, DACL, SACL, timestamps, links, exec, the generic
# `user.*`/`trusted.*`/`system.*` namespace and the `security.*` namespace, all
# with required:true — so anything that cannot be carried across is an error
# rather than a silent downgrade. -x stays on for nested mounts below a
# directory we do copy.
#
# This used to carry --no-preserve=xattrs,security. That was a workaround for
# PEI-180: a squashfs built with no xattr table answers EOPNOTSUPP for the
# whole listing, overlayfs forwards it verbatim, and under -a every class is
# required:true — which switches OFF uucore's EOPNOTSUPP tolerance, so the copy
# aborted partway through a tree it had nothing to preserve from in the first
# place. cp now scopes that tolerance to the SOURCE listing: a filesystem with
# no xattrs at all means "nothing to preserve", while EOPNOTSUPP from the
# DESTINATION is still a real failure. The flag has nothing left to do.
#
# Dropping it also removes a claim that was never true in the strong form the
# comment made. `system.posix_acl_*` would indeed be refused by the target —
# Peios formats ext4 with `default_mntopts = user_xattr`, dropping `acl`,
# because access is decided by descriptors rather than POSIX ACLs — but no
# Peios tree carries one, so silencing the class bought nothing and hid the
# case where the target genuinely cannot keep something. If that ever fires it
# is worth surfacing, not suppressing.
#
# Note that the security descriptor itself does not travel this way: it goes
# via owner/dacl/sacl, and uucore's raw-xattr copy explicitly skips
# `security.peios.sd` so the two paths cannot fight over it.
is_mountpoint() {
    # Pure shell: no awk in the base image, and /proc/mounts is the authority.
    while read -r _source target _rest; do
        [ "$target" = "$1" ] && return 0
    done < /proc/mounts
    return 1
}

echo "$progname: copying the system (this takes a while)"
for entry in /*; do
    name=${entry#/}
    if is_mountpoint "$entry"; then
        echo "$progname:   $entry is a mountpoint — creating it empty"
        mkdir -p "$ROOT_MNT/$name"
        continue
    fi
    cp -ax "$entry" "$ROOT_MNT/"
done

# --- swap the boot packages --------------------------------------------------
# The target is a copy of a LIVE system, so it carries live-boot: a root-mount
# hook that scans for a medium holding rootfs.squashfs. On the installed
# machine, with the medium removed, that hook finds nothing and exits 1 — the
# install would complete and the disk would not boot.
#
# Neither hook reads `root=` to decide whether it is wanted any more. Package
# presence is the selector, and live-boot-irf declares a conflict with
# disk-boot-irf so exactly one can exist in an initramfs. Swapping them is
# therefore not a tidy-up; it is what makes the result bootable.
#
# Order matters and is forced by that conflict: live-boot-irf must be GONE from
# the target's initramfs root before disk-boot-irf can be installed into it.
#
# Two uninstalls rather than one because removal is not cross-root — a package
# manager that cascaded removals into other roots could uninstall something a
# different root still depends on. Installation does cross roots (disk-boot
# declares `disk-boot-irf IN initramfs`), so the single install below places
# both halves in one transaction.
echo "$progname: replacing the live-boot packages with disk-boot"

# The trust ceremony, against the target rather than the live system: the
# repository is a property of the system being managed, and the target is
# about to become one. Its .repo file came across with the copy; §6.5.2 permits
# a non-interactive ceremony precisely because the anchor was supplied through
# a configured channel — here, baked into the image.
peipkg --root "$ROOT_MNT" repo add "$MEDIUM_REPO"     || die "could not establish trust in $MEDIUM_REPO on the target"

peipkg --root "$ROOT_MNT" uninstall live-boot --yes     || die "could not remove live-boot from the target"
peipkg --root "$ROOT_MNT/boot/initramfs" uninstall live-boot-irf --yes     || die "could not remove live-boot-irf from the target's initramfs"

# --allow-stale: a medium is a read-only artifact whose indexes are fixed at
# manufacture, so re-fetching them returns the same index_version and the same
# generated_at — which PSD-009 §6.2.3 defines as a refresh that made no
# progress. An image older than the 30-day trusted age is therefore genuinely
# stale and cannot become fresh. Saying so here, at the one operation that
# knows the staleness is expected, beats disabling the check permanently in the
# repository's configuration.
peipkg --root "$ROOT_MNT" install disk-boot --yes --allow-stale     || die "could not install disk-boot into the target"

# The medium will not be there when the target boots, and a configured
# repository nobody can reach is worse than none: once past its trusted age
# every install and upgrade on the installed machine would demand a refresh
# that can never succeed. Removing it leaves disk-boot ORPHANED in the §6.5.7
# sense — its originating repository is gone, so peipkg will refuse to upgrade
# it until a reachable repository claims it. That is an accurate description of
# a machine installed from a medium, and a far smaller problem than a
# repository that poisons every operation.
peipkg --root "$ROOT_MNT" repo remove "$MEDIUM_REPO"     || die "could not remove $MEDIUM_REPO from the target"

# --- cmdline -----------------------------------------------------------------
# The template supplies everything stable; root= is the per-install part and
# cannot be package data, because it names a filesystem that did not exist
# until two steps ago. /lcl/etc is the operator tree, so the generated file
# belongs there rather than in package-owned /usr.
# First non-empty line: lsblk pads its output, and an empty leading line would
# otherwise sail through as a UUID and produce a cmdline that matches nothing.
root_uuid=$(lsblk -n -o UUID "$root_part" 2>/dev/null | while read -r value; do
    [ -n "$value" ] || continue
    printf '%s\n' "$value"
    break
done)
[ -n "$root_uuid" ] || die "could not read the UUID of $root_part"

cmdline_template="$ROOT_MNT/$CMDLINE_TEMPLATE_REL"
[ -r "$cmdline_template" ] \
    || die "the target has no $CMDLINE_TEMPLATE_REL; the disk-boot install did not land"

mkdir -p "$ROOT_MNT/lcl/etc/boot"
printf '%s root=UUID=%s\n' "$(cat "$cmdline_template")" "$root_uuid" \
    > "$ROOT_MNT/lcl/etc/boot/cmdline"
echo "$progname: cmdline    $(cat "$ROOT_MNT/lcl/etc/boot/cmdline")"

# --- rebuild the initramfs ---------------------------------------------------
# Swapping the packages changed files under the target's initramfs ROOT. What
# actually boots is the cpio ARCHIVE built from that root, and nothing has
# rebuilt it — so without this step the target would carry disk-boot's hook on
# disk and the live hook in the image the firmware loads, which is the same
# unbootable disk as before with more steps.
#
# mkirf takes plain paths, so no chroot is needed. peiso runs it inside one
# only because ITS configured paths are root-relative; here both ends are named
# in full.
#
# The excludes match peiso's. The peipkg database and repository configuration
# are not read at early boot, and the initramfs is decompressed into RAM on
# every boot, so carrying them is a permanent cost for something nothing there
# uses.
# Verified before packing rather than after. A UKI built from an initramfs
# with no root-mount hook produces a machine that boots to prelude's "no hook
# mounted a root filesystem" and stops — recoverable only by someone able to
# build a new UKI. Both halves are checked, because a swap that removed nothing
# is as broken as one that installed nothing: two hooks both mounting
# /mnt/rootfs means the second fails and takes the boot with it.
#
# Checked against the source tree, in pure shell. The obvious alternative —
# looking inside the finished archive — needs tools Peios does not ship: it has
# no grep (peiosutils is a coreutils fork, and grep was never part of
# coreutils) and no gzip. A check calling either would exit 127 and pass
# silently, which is exactly how the "already mounted" guard managed to never
# fire for nine releases.
target_hooks="$ROOT_MNT/boot/initramfs/usr/libexec/prelude/hooks.d"
[ -f "$target_hooks/mount-root-disk.sh" ] \
    || die "the target's initramfs has no disk-boot root-mount hook; the swap did not land"
[ ! -f "$target_hooks/mount-root.sh" ] \
    || die "the target's initramfs still carries live-boot's root-mount hook"

target_initramfs="$ROOT_MNT/system/boot/initramfs.cpio.zst"
echo "$progname: rebuilding the target's initramfs"
mkirf "$ROOT_MNT/boot/initramfs" "$target_initramfs" --compress zstd \
      --exclude var/state/peipkg \
      --exclude lcl/conf/peipkg \
    || die "could not rebuild the target's initramfs"

# --- boot artifact -----------------------------------------------------------
# EFI/BOOT/BOOTX64.EFI is the removable-media fallback path. Firmware boots it
# with no NVRAM entry and no boot manager, which is why installing needs
# neither.
#
# Every input comes from the TARGET: the kernel it will run, the initramfs just
# rebuilt for it, and the cmdline generated from its own disk-boot template.
# The live system supplies only the tools. Anything taken from the live image
# here would be a component the installed machine never agreed to.
mkdir -p "$ESP_MNT/EFI/BOOT"
mkuki --kernel "$ROOT_MNT$kernel" \
      --initramfs "$target_initramfs" \
      --cmdline-file "$ROOT_MNT/lcl/etc/boot/cmdline" \
      --out "$ESP_MNT/EFI/BOOT/BOOTX64.EFI"

sync
echo "$progname: done — reboot with the install medium removed"

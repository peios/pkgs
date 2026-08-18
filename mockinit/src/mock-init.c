// mock-init — a throwaway stand-in for peinit, to shake out real-root PID 1
// problems before peinit is ready.
//
// Why C + libpeios (not another static shell-as-PID1): prelude is static musl,
// so this is the FIRST dynamically-linked binary executed in the off-RAM
// overlay root. Just getting here exercises the whole stack we haven't tested
// post-pivot — the ELF interpreter (glibc's ld-linux) resolving, libc.so.6 and
// libpeios.so.0 loading off the squashfs, and KACS authorizing the mmap/exec of
// each of those SD-less .so files. Then it does the minimum an init must:
// reap children (it's PID 1), bring up scratch tmpfs mounts, and keep a shell.
//
// It is deliberately dumb. Anything it gets wrong (or that KACS/the overlay
// rejects) is a problem we want surfaced now, cheaply, rather than discovered
// when peinit lands.
#define _GNU_SOURCE
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <linux/reboot.h>

#include <peios/token.h>

// libpeios is a Rust cdylib: it leaves rust_eh_personality and _Unwind_Resume
// undefined, expecting a Rust/unwinder runtime from whatever links it (peiosutils,
// being Rust, supplies them). A plain C consumer must provide them itself. They
// are only reached while unwinding a Rust panic, which never crosses our trivial
// FFI calls, so empty stubs are correct in practice and never actually invoked.
// (The binary is built -rdynamic so libpeios.so.0 binds to these at load time.)
void rust_eh_personality(void) {}
void _Unwind_Resume(void *exc) { (void)exc; }

static void say(const char *m) { fprintf(stderr, "mock-init: %s\n", m); }

// The SYSTEM-owned, container+object-inheritable (OICI) default SD that makes a
// fresh SD-less filesystem usable under KACS: without it, DENY_MISSING locks the
// mount and nothing can be created in it. Same descriptor peinit/prelude seed
// (peinit's DEFAULT_SEED_SDDL).
#define SEED_SDDL "O:SYG:SYD:(A;OICI;GA;;;SY)"

// Seed SEED_SDDL onto a mount root by shelling out to the `sd` tool. A real init
// would set this via libpeios directly; this is a throwaway mock, and `sd` is in
// the rootfs (unlike seed-sd, which only ships in the initramfs), so a quick
// exec is the path of least resistance.
static void seed_sd(const char *path) {
    pid_t p = fork();
    if (p == 0) {
        char *argv[] = {"sd", "set", (char *)path, SEED_SDDL, NULL};
        char *envp[] = {"PATH=/bin", NULL};
        execve("/bin/sd", argv, envp);
        perror("mock-init: exec /bin/sd");
        _exit(127);
    }
    if (p < 0) {
        perror("mock-init: fork sd");
        return;
    }
    int st;
    if (waitpid(p, &st, 0) < 0)
        perror("mock-init: waitpid sd");
    else if (st != 0)
        fprintf(stderr, "mock-init: sd set %s -> status 0x%x\n", path, st);
    else
        fprintf(stderr, "mock-init: seeded SD on %s\n", path);
}

// Bring up a scratch tmpfs, then seed its SD so it's actually writable. A fresh
// tmpfs is SD-less; the mount itself succeeds, but KACS DENY_MISSING locks its
// inodes until the seed SD is set (see seed_sd). We log failures and carry on so
// one bad mount doesn't sink the bring-up.
static void scratch_tmpfs(const char *target) {
    if (mkdir(target, 0755) != 0 && errno != EEXIST)
        fprintf(stderr, "mock-init: mkdir %s: %s\n", target, strerror(errno));
    if (mount("tmpfs", target, "tmpfs", 0, NULL) != 0) {
        fprintf(stderr, "mock-init: mount tmpfs %s: %s\n", target, strerror(errno));
        return;
    }
    fprintf(stderr, "mock-init: tmpfs mounted at %s\n", target);
    seed_sd(target);
}

// Launch registryd (loregd) as a system daemon, the way an init brings up a
// service: fork it as a background child; the supervise loop reaps it if it
// dies. A real init (peinit) materializes a LocalService/SYSTEM token and the
// /sbin/registryd role symlink; the mock just execs the binary under our
// inherited boot token to see how far it gets — whether /dev/pkm_registry
// exists, whether we hold SeTcbPrivilege, whether the hives open.
//
// Hive specs follow peinit's convention (REGISTRYD_HIVE_ARGS in its main.rs):
// Name=/var/state/loregd/Name.hive, on the overlay root (writable via the
// hook-seeded tmpfs upper). loregd creates each database AND its directory on
// first boot, so no pre-mkdir is needed. peinit currently registers only
// Machine; we add Users (the per-user / HKU-equivalent hive) too.
static void start_registryd(void) {
    // Create the hive directory. The deployed loregd (v0.21.2) doesn't MkdirAll
    // its own hive parent (a newer loregd does), so we make it. No seed needed,
    // unlike the tmpfs mounts: a new dir under /var/lib inherits a usable SD
    // from that squashfs dir's inheritable ACE (confirmed — loregd opens its
    // hives straight after the mkdir). /var and /var/lib ship in the squashfs.
    if (mkdir("/var/state/loregd", 0755) != 0 && errno != EEXIST)
        fprintf(stderr, "mock-init: mkdir /var/state/loregd: %s\n", strerror(errno));

    pid_t p = fork();
    if (p == 0) {
        char *argv[] = {
            "loregd",
            "Machine=/var/state/loregd/Machine.hive",
            "Users=/var/state/loregd/Users.hive",
            NULL,
        };
        char *envp[] = {"PATH=/sbin:/bin", NULL};
        execve("/sbin/loregd", argv, envp);
        perror("mock-init: exec /sbin/loregd");
        _exit(127);
    }
    if (p < 0)
        perror("mock-init: fork loregd");
    else
        fprintf(stderr, "mock-init: started registryd (loregd) pid=%d\n", (int)p);
}

static volatile sig_atomic_t want_halt = 0;
static void on_term(int sig) { (void)sig; want_halt = 1; }

int main(void) {
    say("real-root PID 1 reached");
    fprintf(stderr, "mock-init: pid=%d\n", (int)getpid());

    // SIGTERM/SIGINT (e.g. ctrl-alt-del forwarded to PID 1) → orderly halt.
    signal(SIGTERM, on_term);
    signal(SIGINT, on_term);

    // libpeios smoke test: open our own token. Proves libpeios.so loaded and a
    // KACS syscall works from the booted root. Failure is informative, not fatal.
    int tok = peios_token_open_self(0, KACS_TOKEN_QUERY);
    if (tok < 0)
        fprintf(stderr, "mock-init: peios_token_open_self: %s\n", strerror(errno));
    else {
        say("peios_token_open_self ok");
        close(tok);
    }

    scratch_tmpfs("/run");
    scratch_tmpfs("/tmp");

    start_registryd();

    // Supervise: keep an interactive shell on the console, reap every child
    // (PID 1 inherits all orphans), respawn the shell if it exits, and halt on a
    // termination signal.
    pid_t shell = -1;
    while (!want_halt) {
        if (shell < 0) {
            shell = fork();
            if (shell == 0) {
                char *argv[] = {"-sh", NULL};
                char *envp[] = {"TERM=linux", "PATH=/bin", "HOME=/root", NULL};
                execve("/bin/sh", argv, envp);
                perror("mock-init: exec /bin/sh");
                _exit(127);
            }
            if (shell < 0) {
                perror("mock-init: fork");
                break;
            }
        }

        int status;
        pid_t w = waitpid(-1, &status, 0);
        if (w < 0) {
            if (errno == EINTR)
                continue; // re-check want_halt
            perror("mock-init: waitpid");
            break;
        }
        if (w == shell) {
            fprintf(stderr, "mock-init: shell exited (0x%x); respawning\n", status);
            shell = -1;
        } else {
            // A daemon (registryd) or reaped orphan exited — log it so a
            // registryd crash is visible rather than silent.
            fprintf(stderr, "mock-init: child %d exited (0x%x)\n", (int)w, status);
        }
    }

    say("halting");
    sync();
    reboot(LINUX_REBOOT_CMD_POWER_OFF);
    for (;;)
        pause();
}

/* SPDX-License-Identifier: GPL-3.0-or-later
 * Run as /init in a disposable KACS guest. Tests the exact compiled adapter.
 */
#define _GNU_SOURCE
#include "peios.h"
#include <peios/file.h>
#include <peios/security.h>
#include <peios/token.h>
#include <errno.h>
#include <fcntl.h>
#include <ftw.h>
#include <pty.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
static unsigned checks;
static const void *runtime_sd;
static size_t runtime_sd_len;
static int grant_runtime(const char *path, const struct stat *st, int type, struct FTW *f) {
    (void)st; (void)type; (void)f;
    return peios_file_set_sd(AT_FDCWD, path, KACS_SECINFO_DACL, runtime_sd, runtime_sd_len, 0);
}
static void check(int ok, const char *why) {
    checks++;
    if (!ok) {
        printf("NANO_FACS_FAIL: %s: %s\n", why, strerror(errno));
        fflush(NULL); peios_token_revert(); reboot(RB_POWER_OFF); _exit(1);
    }
}
static int token(const char *name) {
    unsigned char sid[PEIOS_SID_MAX_BYTES];
    ssize_t n = peios_sid_parse_string(sid, sizeof(sid), name);
    peios_token_builder *b = peios_token_builder_new();
    check(n > 0 && b, "token builder");
    struct peios_session_spec session = { .logon_type = KACS_LOGON_TYPE_INTERACTIVE,
        .auth_package = "nano-test", .user_sid = sid, .user_sid_len = n };
    uint64_t id;
    check(peios_session_create(&session, &id) == 0, "create logon session");
    peios_token_builder_session(b, id);
    unsigned char world[PEIOS_SID_MAX_BYTES];
    ssize_t wn = peios_sid_well_known(world, sizeof(world), PEIOS_WKS_EVERYONE);
    peios_token_builder_add_group(b, world, wn, 7);
    peios_token_builder_user(b, sid, n);
    peios_acl_builder *acl = peios_acl_builder_new();
    peios_acl_builder_allow(acl, sid, n, KACS_ACCESS_GENERIC_ALL, 0);
    size_t dlen;
    const void *dacl = peios_acl_builder_bytes(acl, &dlen);
    peios_token_builder_default_dacl(b, dacl, dlen);
    peios_acl_builder_free(acl);
    peios_token_builder_type(b, KACS_TOKEN_TYPE_IMPERSONATION, KACS_IMLEVEL_IMPERSONATION);
    peios_token_builder_integrity(b, PEIOS_IL_SYSTEM);
    /* Same compatibility IDs: authorization must distinguish SIDs. */
    peios_token_builder_projected_ids(b, 1000, 1000);
    int fd = peios_token_builder_create(b);
    peios_token_builder_free(b);
    check(fd >= 0, "create test token");
    return fd;
}
static void content(const char *name, const char *expected) {
    char buf[80] = {0};
    int fd = open(name, O_RDONLY);
    check(fd >= 0, "open content");
    check(read(fd, buf, sizeof(buf) - 1) >= 0 && !strcmp(buf, expected), "content unchanged");
    close(fd);
}
static void expect(int fd, const char *word) {
    char out[65536] = {0}; size_t len = 0;
    for (int i = 0; i < 100; i++) {
        struct pollfd p = { .fd = fd, .events = POLLIN };
        if (poll(&p, 1, 100) <= 0) continue;
        ssize_t n = read(fd, out + len, sizeof(out) - len - 1);
        if (n <= 0) break;
        len += n; out[len] = 0;
        if (strstr(out, word)) return;
        if (len > sizeof(out) / 2) { memmove(out, out + len/2, len - len/2); len -= len/2; }
    }
    printf("terminal waiting for %s: %s\n", word, out);
    check(0, "nano terminal expectation");
}
static void sendkeys(int fd, const char *keys) {
    check(write(fd, keys, strlen(keys)) == (ssize_t)strlen(keys), "terminal input");
}
static void editor(int primary, int emergency) {
    int master, status;
    struct winsize ws = { .ws_row = 24, .ws_col = 80 };
    pid_t pid = forkpty(&master, NULL, NULL, &ws);
    check(pid >= 0, "nano forkpty");
    if (pid == 0) {
        if (peios_token_install(primary) < 0) { perror("install editor token"); _exit(126); }
        setenv("TERM", "xterm", 1); setenv("HOME", "/work/home", 1);
        setenv("LC_ALL", "C", 1);
        execl("/nano", "nano", "--ignorercfiles", "--backup", "--historylog",
              "--positionlog", "/work/document", NULL);
        perror("exec nano"); _exit(127);
    }
    expect(master, "original");
    sendkeys(master, emergency ? "unsaved" : "added\r");
    if (emergency) {
        expect(master, "unsaved");
        check(kill(pid, SIGHUP) == 0, "emergency save signal");
    } else {
        sendkeys(master, "\x17"); expect(master, "Search");
        sendkeys(master, "original\r");
        expect(master, "original");
        sendkeys(master, "\x0f"); expect(master, "Write to File");
        sendkeys(master, "\r"); expect(master, "Wrote");
        sendkeys(master, "\x18");
    }
    /* Drain so terminal output cannot block shutdown. */
    struct pollfd p = { .fd = master, .events = POLLIN };
    for (int i = 0; i < 100; i++) {
        if (waitpid(pid, &status, WNOHANG) == pid) {
            close(master);
            check(WIFEXITED(status) && (emergency || WEXITSTATUS(status) == 0), "nano exit");
            return;
        }
        if (poll(&p, 1, 100) > 0) { char buf[8192]; ssize_t drained = read(master, buf, sizeof(buf)); if (drained < 0 && errno != EIO) break; }
    }
    kill(pid, SIGKILL); check(0, "nano exit timeout");
}
int main(void) {
    mkdir("/proc", 0755); mount("proc", "/proc", "proc", 0, NULL);
    mkdir("/dev", 0755); mount("devtmpfs", "/dev", "devtmpfs", 0, NULL);
    
    mkdir("/work", 0777);
    check(mount("tmpfs", "/work", "tmpfs", 0, "mode=0777") == 0, "mount work");
    unsigned char system[PEIOS_SID_MAX_BYTES], everyone[PEIOS_SID_MAX_BYTES];
    ssize_t sn = peios_sid_well_known(system, sizeof(system), PEIOS_WKS_SYSTEM);
    ssize_t en = peios_sid_well_known(everyone, sizeof(everyone), PEIOS_WKS_EVERYONE);
    peios_acl_builder *acl = peios_acl_builder_new();
    peios_sd_builder *sd = peios_sd_builder_new();
    check(sn > 0 && en > 0 && acl && sd, "SD builders");
    peios_acl_builder_allow(acl, everyone, en, KACS_ACCESS_GENERIC_ALL,
        KACS_ACE_FLAG_OBJECT_INHERIT | KACS_ACE_FLAG_CONTAINER_INHERIT);
    size_t alen, slen;
    const void *ab = peios_acl_builder_bytes(acl, &alen);
    peios_sd_builder_owner(sd, system, sn);
    peios_sd_builder_dacl(sd, ab, alen);
    const void *sb = peios_sd_builder_bytes(sd, &slen);
    int dir = open("/work", O_PATH | O_DIRECTORY);
    struct peios_mount_policy policy = { .policy = KACS_MOUNT_POLICY_SYNTHESIZE_EPHEMERAL,
        .template_sd = sb, .template_sd_len = slen };
    check(dir >= 0 && peios_mount_set_policy(dir, &policy) == 0, "mount policy");
    check(peios_fd_set_sd(dir, KACS_SECINFO_OWNER | KACS_SECINFO_DACL, sb, slen) == 0, "permissive parent");
    close(dir);
    dir = open("/dev", O_PATH | O_DIRECTORY);
    check(dir >= 0 && peios_mount_set_policy(dir, &policy) == 0, "devtmpfs test policy");
    check(peios_fd_set_sd(dir, KACS_SECINFO_OWNER | KACS_SECINFO_DACL, sb, slen) == 0, "dev root SD");
    close(dir);
    check(mkdir("/dev/pts", 0755) == 0, "devpts mountpoint");
    check(mount("devpts", "/dev/pts", "devpts", 0, "mode=0620,ptmxmode=0666") == 0, "mount devpts");
    dir = open("/dev/pts", O_PATH | O_DIRECTORY);
    check(dir >= 0 && peios_mount_set_policy(dir, &policy) == 0, "devpts test policy");
    close(dir);
    check(peios_file_set_sd(AT_FDCWD, "/", KACS_SECINFO_DACL, sb, slen, 0) == 0, "root traversal policy");
    runtime_sd = sb; runtime_sd_len = slen;
    check(grant_runtime("/nano", NULL, 0, NULL) == 0, "nano executable DACL");
    check(nftw("/lib", grant_runtime, 10, FTW_PHYS) == 0, "library DACLs");
    check(nftw("/lib64", grant_runtime, 10, FTW_PHYS) == 0, "loader DACLs");
    check(nftw("/usr", grant_runtime, 10, FTW_PHYS) == 0, "terminfo DACLs");
    int a = token("S-1-5-21-1181-1"), b = token("S-1-5-21-1181-2");
    check(peios_token_impersonate(a) == 0, "identity A");
    int self = peios_token_open_self(0, KACS_TOKEN_QUERY);
    check(self >= 0, "query effective token"); close(self);
    check(access("/work", W_OK) == 0, "parent create access");
    int fd = nano_private_open("/work/secret", O_RDWR | O_CREAT | O_EXCL, 0);
    check(fd >= 0, "private create in public parent");
    check(write(fd, "secret", 6) == 6, "write private content");
    close(fd);
    check(nano_private_mkdir("/work/state/") == 0, "create private state directory");
    check(nano_private_mkdir("/work/state/") == 0, "validate existing state directory");
    char temp[] = "/work/nano.XXXXXX.txt";
    fd = nano_private_mkstemps(temp, 4);
    check(fd >= 0 && !strcmp(temp + strlen(temp) - 4, ".txt"), "private random scratch with suffix");
    close(fd);
    check(peios_token_revert() == 0 && peios_token_impersonate(b) == 0, "identity B");
    check(open("/work/secret", O_RDONLY) < 0 && errno == EACCES, "other SID cannot read secret");
    check(open("/work/secret", O_WRONLY) < 0 && errno == EACCES, "other SID cannot write secret");
    check(open(temp, O_RDONLY) < 0 && errno == EACCES, "other SID cannot read scratch");
    check(nano_private_mkdir("/work/state/") < 0, "other SID cannot adopt state directory");
    check(peios_token_revert() == 0 && peios_token_impersonate(a) == 0, "restore identity A");
    FILE *f = nano_private_fopen("/work/state/history", "wb");
    check(f != NULL && fputs("history", f) >= 0 && fclose(f) == 0, "history save");
    f = nano_private_fopen("/work/state/history", "rb");
    check(f != NULL && fgetc(f) == 'h', "history load"); fclose(f);
    fd = open("/work/public", O_CREAT | O_WRONLY, 0600);
    check(fd >= 0 && write(fd, "untouched", 9) == 9, "mode 0600 under public inheritance"); close(fd);
    check(nano_private_fopen("/work/public", "wb") == NULL, "reject public DACL before truncation");
    content("/work/public", "untouched");
    check(peios_token_revert() == 0, "privileged symlink setup");
    check(symlink("secret", "/work/symlink") == 0, "create symlink");
    check(peios_token_impersonate(a) == 0, "unprivileged symlink test");
    check(nano_private_fopen("/work/symlink", "wb") == NULL, "reject history symlink");
    check(peios_token_revert() == 0, "privileged directory link setup");
    check(symlink("state", "/work/state-link") == 0, "directory symlink");
    check(peios_token_impersonate(a) == 0, "unprivileged directory link test");
    check(nano_private_mkdir("/work/state-link/") < 0, "reject directory symlink with trailing slash");
    check(link("/work/secret", "/work/hardlink") == 0, "create hardlink");
    check(nano_private_fopen("/work/secret", "wb") == NULL, "reject multi-link history before truncation");
    content("/work/hardlink", "secret");
    unlink("/work/hardlink");
    f = nano_private_fopen("/work/secret", "wb");
    check(f != NULL && fputs("updated", f) >= 0 && fclose(f) == 0, "validated truncation");
    content("/work/secret", "updated");
    check(peios_token_revert() == 0, "restore system");
    /* Exercise the installed editor as a principal with no security privileges. */
    int primary = peios_token_duplicate(a, KACS_TOKEN_ALL_ACCESS,
        KACS_TOKEN_TYPE_PRIMARY, KACS_IMLEVEL_IMPERSONATION);
    check(primary >= 0, "editor primary token");
    mkdir("/work/home", 0777);
    fd = open("/work/document", O_CREAT | O_WRONLY, 0444);
    check(fd >= 0 && write(fd, "original\n", 9) == 9, "document seed"); close(fd);
    peios_acl_builder_reset(acl);
    peios_acl_builder_allow(acl, system, sn, KACS_ACCESS_GENERIC_ALL, 0);
    unsigned char asid[PEIOS_SID_MAX_BYTES];
    ssize_t an = peios_sid_parse_string(asid, sizeof(asid), "S-1-5-21-1181-1");
    peios_acl_builder_allow(acl, asid, an,
        KACS_FILE_READ_DATA | KACS_FILE_WRITE_DATA | KACS_FILE_READ_ATTRIBUTES | KACS_ACCESS_SYNCHRONIZE, 0);
    ab = peios_acl_builder_bytes(acl, &alen);
    peios_sd_builder_reset(sd); peios_sd_builder_dacl(sd, ab, alen);
    sb = peios_sd_builder_bytes(sd, &slen);
    check(peios_file_set_sd(AT_FDCWD, "/work/document", KACS_SECINFO_DACL, sb, slen, 0) == 0,
          "document writable without security management rights");
    unsigned char before[4096], after[4096];
    ssize_t before_len = peios_file_get_sd(AT_FDCWD, "/work/document", 15, before, sizeof(before), 0);
    check(before_len > 0, "read full document SD as verifier");
    struct stat oldstat, newstat;
    check(stat("/work/document", &oldstat) == 0, "original inode");
    editor(primary, 0);
    ssize_t after_len = peios_file_get_sd(AT_FDCWD, "/work/document", 15, after, sizeof(after), 0);
    check(after_len == before_len && !memcmp(before, after, before_len), "save preserves full SD");
    check(stat("/work/document", &newstat) == 0 && newstat.st_ino == oldstat.st_ino,
          "save retains inode");
    content("/work/document", "added\noriginal\n");
    check(peios_token_impersonate(a) == 0, "inspect editor backup as its owner");
    content("/work/document~", "original\n");
    f = nano_private_fopen("/work/home/.local/share/nano/search_history", "rb");
    check(f != NULL, "actual nano private search history"); fclose(f);
    f = nano_private_fopen("/work/home/.local/share/nano/filepos_history", "rb");
    check(f != NULL, "actual nano private position history"); fclose(f);
    check(peios_token_revert() == 0, "restore verifier");
    editor(primary, 1);
    check(peios_token_impersonate(a) == 0, "inspect actual recovery");
    f = nano_private_fopen("/work/document.save", "rb");
    check(f != NULL, "actual nano private emergency file"); fclose(f);
    check(peios_token_revert() == 0 && peios_token_impersonate(b) == 0, "other principal");
    check(open("/work/document~", O_RDONLY) < 0 && errno == EACCES, "editor backup isolated");
    check(open("/work/document.save", O_RDONLY) < 0 && errno == EACCES, "editor recovery isolated");
    check(peios_token_revert() == 0, "final revert");
    printf("NANO_FACS_PASS: %u checks\n", checks);
    fflush(NULL); reboot(RB_POWER_OFF); return 0;
}

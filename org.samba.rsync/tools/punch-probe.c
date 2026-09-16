#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
/* Exit 0: deallocation observed; 1: filesystem lacks capability; 2: probe error. */
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    int fd = open(argv[1], O_CREAT|O_EXCL|O_RDWR, 0600);
    if (fd < 0) { perror("open punch probe"); return 2; }
    int result = 2;
    char bytes[65536]; memset(bytes, 255, sizeof bytes);
    struct stat before, after;
    if (write(fd, bytes, sizeof bytes) != sizeof bytes || fstat(fd, &before)) goto done;
    if (fallocate(fd, FALLOC_FL_KEEP_SIZE|FALLOC_FL_PUNCH_HOLE, 0, sizeof bytes)) {
        if (errno == EOPNOTSUPP || errno == ENOSYS || errno == EINVAL) result = 1;
        goto done;
    }
    if (fstat(fd, &after)) goto done;
    result = after.st_blocks < before.st_blocks ? 0 : 1;
done:
    if (result == 2) perror("punch probe");
    if (close(fd) || unlink(argv[1])) return 2;
    return result;
}

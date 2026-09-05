/* Bring up loopback in peiroot's otherwise empty private network namespace. */
#include <errno.h>
#include <net/if.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <unistd.h>

int main(void)
{
    struct ifreq ifr;
    int fd;

    fd = socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (fd < 0) {
        perror("peiroot: socket for loopback setup");
        return 1;
    }

    memset(&ifr, 0, sizeof(ifr));
    memcpy(ifr.ifr_name, "lo", sizeof("lo"));
    if (ioctl(fd, SIOCGIFFLAGS, &ifr) < 0) {
        perror("peiroot: read loopback flags");
        close(fd);
        return 1;
    }
    ifr.ifr_flags |= IFF_UP;
    if (ioctl(fd, SIOCSIFFLAGS, &ifr) < 0) {
        perror("peiroot: bring loopback up");
        close(fd);
        return 1;
    }
    if (close(fd) < 0) {
        perror("peiroot: close loopback socket");
        return 1;
    }
    return 0;
}

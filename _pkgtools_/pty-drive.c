/* pty-drive: run a command on a pseudo-terminal and script it (PEI-613).
 *
 *   cc -o pty-drive pty-drive.c
 *   pty-drive [-t SECONDS] SCRIPT -- COMMAND [ARG...]
 *
 * Interactive gates (Readline line editing and history in particular) need a
 * real terminal: a pipe makes the program fall back to plain line reads. This
 * is a deliberately tiny expect(1): SCRIPT is read line by line,
 *
 *   send TEXT     write TEXT to the terminal
 *   expect TEXT   wait until TEXT appears in the output after the previous
 *                 expect's match
 *   # ...         comment; blank lines are ignored
 *
 * TEXT takes C escapes: \r \n \t \e \\ \xHH (so Up-arrow is "\e[A" and
 * Ctrl-A is "\x01"). After the script, the driver closes the terminal and
 * waits for the command. The whole transcript goes to stdout.
 *
 * Exit status: the command's own status once every expect matched; 124 on a
 * timeout (default 30s, for the whole run); 125 on a usage or system error.
 * A failed expect reports the text it waited for on stderr.
 *
 * Needs only libc: forkpty is in glibc since 2.34.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <poll.h>
#include <pty.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static int master = -1;
static pid_t child = -1;
static char *out;          /* transcript so far */
static size_t out_len, out_cap;
static size_t mark;        /* expects search from here */
static struct timespec deadline;

static void fail(int status, const char *fmt, const char *arg)
{
	fprintf(stderr, "pty-drive: ");
	fprintf(stderr, fmt, arg);
	fputc('\n', stderr);
	fwrite(out, 1, out_len, stdout);
	if (child > 0)
		kill(child, SIGKILL);
	exit(status);
}

static int remaining_ms(void)
{
	struct timespec now;
	clock_gettime(CLOCK_MONOTONIC, &now);
	long ms = (deadline.tv_sec - now.tv_sec) * 1000 +
		  (deadline.tv_nsec - now.tv_nsec) / 1000000;
	return ms > 0 ? (int)ms : 0;
}

/* Read what the terminal has, waiting at most ms. Returns 0 at EOF. */
static int pump(int ms)
{
	struct pollfd p = { .fd = master, .events = POLLIN };
	int r = poll(&p, 1, ms);
	if (r < 0 && errno != EINTR)
		fail(125, "poll: %s", strerror(errno));
	if (r <= 0)
		return 1;
	char buf[4096];
	ssize_t n = read(master, buf, sizeof buf);
	if (n <= 0)
		return 0; /* EIO once the child side is closed */
	if (out_len + (size_t)n + 1 > out_cap) {
		out_cap = (out_len + (size_t)n + 1) * 2;
		out = realloc(out, out_cap);
		if (!out)
			fail(125, "%s", "out of memory");
	}
	memcpy(out + out_len, buf, (size_t)n);
	out_len += (size_t)n;
	out[out_len] = '\0';
	return 1;
}

static size_t unescape(const char *in, char *dst)
{
	size_t n = 0;
	for (; *in; in++) {
		if (*in != '\\' || !in[1]) {
			dst[n++] = *in;
			continue;
		}
		switch (*++in) {
		case 'r': dst[n++] = '\r'; break;
		case 'n': dst[n++] = '\n'; break;
		case 't': dst[n++] = '\t'; break;
		case 'e': dst[n++] = '\033'; break;
		case '\\': dst[n++] = '\\'; break;
		case 'x': {
			char hex[3] = { 0 };
			if (!in[1] || !in[2])
				fail(125, "bad \\x escape in %s", in);
			hex[0] = in[1];
			hex[1] = in[2];
			dst[n++] = (char)strtol(hex, NULL, 16);
			in += 2;
			break;
		}
		default:
			fail(125, "unknown escape \\%s", in);
		}
	}
	return n;
}

static void expect(const char *text, size_t len)
{
	for (;;) {
		if (out_len >= mark + len) {
			char *hit = memmem(out + mark, out_len - mark, text, len);
			if (hit) {
				mark = (size_t)(hit - out) + len;
				return;
			}
		}
		int ms = remaining_ms();
		if (ms == 0)
			fail(124, "timed out waiting for \"%s\"", text);
		if (!pump(ms))
			fail(1, "terminal closed while waiting for \"%s\"", text);
	}
}

static void send(const char *text, size_t len)
{
	while (len > 0) {
		ssize_t n = write(master, text, len);
		if (n < 0 && errno != EINTR)
			fail(125, "write: %s", strerror(errno));
		if (n > 0) {
			text += n;
			len -= (size_t)n;
		}
	}
}

int main(int argc, char **argv)
{
	int timeout = 30;
	int opt;
	while ((opt = getopt(argc, argv, "+t:")) != -1) {
		if (opt != 't')
			return 125;
		timeout = atoi(optarg);
	}
	if (argc - optind < 3 || strcmp(argv[optind + 1], "--") != 0) {
		fprintf(stderr, "usage: pty-drive [-t SECONDS] SCRIPT -- COMMAND [ARG...]\n");
		return 125;
	}
	FILE *script = fopen(argv[optind], "r");
	if (!script) {
		perror(argv[optind]);
		return 125;
	}
	clock_gettime(CLOCK_MONOTONIC, &deadline);
	deadline.tv_sec += timeout;

	struct winsize ws = { .ws_row = 24, .ws_col = 80 };
	child = forkpty(&master, NULL, NULL, &ws);
	if (child < 0) {
		perror("forkpty");
		return 125;
	}
	if (child == 0) {
		execvp(argv[optind + 2], argv + optind + 2);
		perror(argv[optind + 2]);
		_exit(127);
	}

	char *line = NULL;
	size_t cap = 0;
	ssize_t got;
	while ((got = getline(&line, &cap, script)) >= 0) {
		if (got > 0 && line[got - 1] == '\n')
			line[--got] = '\0';
		if (got == 0 || line[0] == '#')
			continue;
		char *buf = malloc((size_t)got + 1);
		if (!buf)
			fail(125, "%s", "out of memory");
		if (strncmp(line, "send ", 5) == 0) {
			send(buf, unescape(line + 5, buf));
		} else if (strncmp(line, "expect ", 7) == 0) {
			size_t n = unescape(line + 7, buf);
			buf[n] = '\0';
			expect(buf, n);
		} else {
			fail(125, "bad script line: %s", line);
		}
		free(buf);
	}
	fclose(script);

	/* Drain until the command closes its side of the terminal. */
	while (remaining_ms() > 0 && pump(remaining_ms()))
		;
	int status;
	for (;;) {
		pid_t r = waitpid(child, &status, WNOHANG);
		if (r == child)
			break;
		if (remaining_ms() == 0)
			fail(124, "%s", "timed out waiting for the command to exit");
		struct timespec tick = { 0, 20 * 1000000 };
		nanosleep(&tick, NULL);
	}
	child = -1;
	fwrite(out, 1, out_len, stdout);
	if (WIFEXITED(status))
		return WEXITSTATUS(status);
	return 128 + WTERMSIG(status);
}

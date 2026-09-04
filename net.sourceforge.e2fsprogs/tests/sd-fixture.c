#include <errno.h>
#include <peios/security.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/xattr.h>

static void die(const char *what)
{
	perror(what);
	exit(EXIT_FAILURE);
}

static void *parse_sddl(const char *sddl, size_t *len)
{
	ssize_t need = peios_sddl_parse_sd(NULL, 0, sddl);
	void *sd;

	if (need < 0)
		die("peios_sddl_parse_sd probe");
	sd = malloc((size_t)need);
	if (!sd)
		die("malloc");
	if (peios_sddl_parse_sd(sd, (size_t)need, sddl) != need)
		die("peios_sddl_parse_sd");
	*len = (size_t)need;
	return sd;
}

static void write_bytes(const char *path, const void *buf, size_t len)
{
	FILE *fp = fopen(path, "wb");

	if (!fp)
		die("fopen");
	if (fwrite(buf, 1, len, fp) != len)
		die("fwrite");
	if (fclose(fp))
		die("fclose");
}

int main(int argc, char **argv)
{
	void *parent, *child, *result;
	size_t parent_len, child_len;
	ssize_t result_len;

	if (argc == 4 && !strcmp(argv[1], "parse")) {
		result = parse_sddl(argv[2], &child_len);
		write_bytes(argv[3], result, child_len);
		free(result);
		return 0;
	}
	if (argc == 4 && !strcmp(argv[1], "stage")) {
		result = parse_sddl(argv[2], &child_len);
		if (lsetxattr(argv[3], "user.peios.sd", result, child_len, 0))
			die("lsetxattr");
		free(result);
		return 0;
	}
	if (argc == 6 && !strcmp(argv[1], "inherit")) {
		parent = parse_sddl(argv[2], &parent_len);
		child = parse_sddl(argv[3], &child_len);
		result_len = peios_sd_reinherit(NULL, 0, parent, parent_len,
						 child, child_len, atoi(argv[4]));
		if (result_len < 0)
			die("peios_sd_reinherit probe");
		result = malloc((size_t)result_len);
		if (!result)
			die("malloc");
		if (peios_sd_reinherit(result, (size_t)result_len,
					parent, parent_len, child, child_len,
					atoi(argv[4])) != result_len)
			die("peios_sd_reinherit");
		write_bytes(argv[5], result, (size_t)result_len);
		free(parent);
		free(child);
		free(result);
		return 0;
	}
	fprintf(stderr,
		"usage: %s parse SDDL FILE | stage SDDL PATH | "
		"inherit PARENT CHILD IS_CONTAINER FILE\n", argv[0]);
	return EXIT_FAILURE;
}

/* Composed-image static NSS probe.

   Build this against the exact org.gnu.glibc-static revision in the image:

     cc -O2 -static composed-nss.c -o glibc-static-nss-probe

   The resulting executable is deliberately not hermetic.  Its NSS calls must
   dlopen the image's matching nss-peios and nss-peios-net providers.  Run it
   through composed-nss.sh only after authd and resolvd are ready.  */

#include <grp.h>
#include <netdb.h>
#include <pwd.h>
#include <string.h>

int
main (void)
{
  struct passwd *pwd = getpwnam ("SYSTEM");
  if (pwd == 0 || pwd->pw_uid != 0)
    return 10;
  pwd = getpwuid (0);
  if (pwd == 0 || strcmp (pwd->pw_name, "SYSTEM") != 0)
    return 11;

  struct group *grp = getgrnam ("Everyone");
  if (grp == 0 || grp->gr_gid != 100)
    return 12;
  grp = getgrgid (100);
  if (grp == 0 || strcmp (grp->gr_name, "Everyone") != 0)
    return 13;

  struct addrinfo hints = { .ai_family = AF_UNSPEC };
  struct addrinfo *result = 0;
  int status = getaddrinfo ("localhost", 0, &hints, &result);
  if (result != 0)
    freeaddrinfo (result);
  return status == 0 ? 0 : 14;
}

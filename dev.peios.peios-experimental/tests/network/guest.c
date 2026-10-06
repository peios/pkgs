/* SPDX-License-Identifier: MIT
 * Disposable VM integration: ordinary echo and curl FACS state.
 * PNP denial on real echo traffic is exercised by pnp_kunit_echo_on_wire.
 */
#define _GNU_SOURCE
#include <peios/file.h>
#include <peios/security.h>
#include <peios/token.h>
#include <peios/registry.h>
#include <pkm/pnp.h>
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <ftw.h>
#include <net/if.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
static unsigned checks;
static const void *world_sd; static size_t world_len;
static void check(int ok, const char *why) {
 ++checks; if(ok)return;
 printf("NETWORK_FAIL: %s: %s\n",why,strerror(errno));fflush(NULL);reboot(RB_POWER_OFF);_exit(1);
}
static int grant(const char *path,const struct stat *st,int type,struct FTW *f) {
 (void)st;(void)type;(void)f;
 return peios_file_set_sd(AT_FDCWD,path,KACS_SECINFO_DACL,world_sd,world_len,0);
}
static int principal(const char *name) {
 unsigned char sid[PEIOS_SID_MAX_BYTES],world[PEIOS_SID_MAX_BYTES];
 ssize_t n=peios_sid_parse_string(sid,sizeof(sid),name),wn=peios_sid_well_known(world,sizeof(world),PEIOS_WKS_EVERYONE);
 peios_token_builder *b=peios_token_builder_new();check(n>0&&wn>0&&b,"principal builder");
 struct peios_session_spec spec={.logon_type=KACS_LOGON_TYPE_INTERACTIVE,.auth_package="network-test",.user_sid=sid,.user_sid_len=n};uint64_t id;
 check(!peios_session_create(&spec,&id),"principal session");
 peios_token_builder_session(b,id);peios_token_builder_user(b,sid,n);peios_token_builder_add_group(b,world,wn,7);
 peios_token_builder_projected_ids(b,1000,1000);peios_token_builder_integrity(b,PEIOS_IL_SYSTEM);
 peios_token_builder_type(b,KACS_TOKEN_TYPE_PRIMARY,KACS_IMLEVEL_IMPERSONATION);
 int fd=peios_token_builder_create(b);peios_token_builder_free(b);check(fd>=0,"principal token");return fd;
}
static int run(int token,char *const argv[]) {
 pid_t pid=fork();check(pid>=0,"fork command");
 if(!pid){if(peios_token_install(token)<0){perror("install token");_exit(126);}execv(argv[0],argv);perror("exec");_exit(127);}
 int status;check(waitpid(pid,&status,0)==pid,"wait command");check(WIFEXITED(status),"command normal exit");return WEXITSTATUS(status);
}
static void ping(int token,int v6,int allowed) {
 char *args[]={"/ping",v6?"-6":"-4","-n","-c","1","-W","1",v6?"::1":"127.0.0.1",NULL};
 int rc=run(token,args);check(allowed?rc==0:rc!=0,allowed?"unprivileged ping passes":"PNP blocks unprivileged ping");
}
int main(void) {
 setvbuf(stdout,NULL,_IONBF,0);
 mkdir("/proc",0755);check(!mount("proc","/proc","proc",0,NULL),"mount proc");
 mkdir("/dev",0755);check(!mount("devtmpfs","/dev","devtmpfs",0,NULL),"mount dev");
 mkdir("/work",0777);check(!mount("tmpfs","/work","tmpfs",0,"mode=0777"),"mount work");
 unsigned char world[PEIOS_SID_MAX_BYTES],system[PEIOS_SID_MAX_BYTES];
 ssize_t wn=peios_sid_well_known(world,sizeof(world),PEIOS_WKS_EVERYONE),sn=peios_sid_well_known(system,sizeof(system),PEIOS_WKS_SYSTEM);
 peios_acl_builder *acl=peios_acl_builder_new();peios_sd_builder *sd=peios_sd_builder_new();
 peios_acl_builder_allow(acl,world,wn,KACS_ACCESS_GENERIC_ALL,KACS_ACE_FLAG_OBJECT_INHERIT|KACS_ACE_FLAG_CONTAINER_INHERIT);
 size_t len;const void *ab=peios_acl_builder_bytes(acl,&len);peios_sd_builder_owner(sd,system,sn);peios_sd_builder_dacl(sd,ab,len);world_sd=peios_sd_builder_bytes(sd,&world_len);check(world_sd!=NULL,"fixture SD");
 struct peios_mount_policy policy={.policy=KACS_MOUNT_POLICY_SYNTHESIZE_EPHEMERAL,.template_sd=world_sd,.template_sd_len=world_len};
 int fd=open("/work",O_PATH|O_DIRECTORY);check(fd>=0&&!peios_mount_set_policy(fd,&policy),"work policy");close(fd);check(!grant("/work",NULL,0,NULL),"work DACL");
 check(!grant("/",NULL,0,NULL),"root traversal");
 check(!nftw("/usr",grant,16,FTW_PHYS),"runtime DACL");check(!nftw("/lib64",grant,16,FTW_PHYS),"loader DACL");check(!grant("/ping",NULL,0,NULL),"ping DACL");check(!grant("/curl",NULL,0,NULL),"curl DACL");
 int ctl=socket(AF_INET,SOCK_DGRAM,0);struct ifreq ifr={0};strcpy(ifr.ifr_name,"lo");
 check(ctl>=0&&!ioctl(ctl,SIOCGIFFLAGS,&ifr),"read loopback");ifr.ifr_flags|=IFF_UP;check(!ioctl(ctl,SIOCSIFFLAGS,&ifr),"enable loopback");close(ctl);
 int a=principal("S-1-5-21-1184-1"),b=principal("S-1-5-21-1184-2");
 /* A raw socket remains forbidden even though echo datagrams are available. */
 pid_t child=fork();check(child>=0,"fork raw denial");if(!child){if(peios_token_install(a)<0)_exit(2);int raw=socket(AF_INET,SOCK_RAW,IPPROTO_ICMP);_exit(raw<0&&errno==EPERM?0:1);}int st;waitpid(child,&st,0);check(WIFEXITED(st)&&WEXITSTATUS(st)==0,"raw ICMP remains restricted");
 ping(a,0,1);ping(a,1,1);
 fd=open("/work/input",O_WRONLY|O_CREAT,0666);check(fd>=0&&write(fd,"fixture\n",8)==8,"input file");close(fd);
 int server=socket(AF_INET,SOCK_STREAM,0);
 struct sockaddr_in endpoint={.sin_family=AF_INET,.sin_addr.s_addr=htonl(INADDR_LOOPBACK)};
 socklen_t endpoint_len=sizeof(endpoint);
 check(server>=0&&!bind(server,(void*)&endpoint,sizeof(endpoint))&&!listen(server,1)&&!getsockname(server,(void*)&endpoint,&endpoint_len),"HTTP listener");
 pid_t responder=fork();check(responder>=0,"HTTP responder");
 if(!responder){int c=accept(server,NULL,NULL);char request[4096];if(c<0||read(c,request,sizeof(request))<=0)_exit(1);
  const char response[]="HTTP/1.0 200 OK\r\nSet-Cookie: secret=value; Path=/\r\nContent-Length: 8\r\n\r\nfixture\n";
  ssize_t sent=write(c,response,sizeof(response)-1);close(c);close(server);_exit(sent==(ssize_t)sizeof(response)-1?0:1);}
 close(server);char url[128];snprintf(url,sizeof(url),"http://127.0.0.1:%u/",ntohs(endpoint.sin_port));
 char *curl[]={"/curl","--verbose","--show-error","--cookie","secret=value","--cookie-jar","/work/cookies","--hsts","/work/hsts","--alt-svc","/work/alt-svc",url,NULL};
 check(run(a,curl)==0,"native curl state write");
 check(waitpid(responder,&st,0)==responder&&WIFEXITED(st)&&WEXITSTATUS(st)==0,"HTTP response");
 for(unsigned i=0;i<3;i++) {
  const char *names[]={"/work/cookies","/work/hsts","/work/alt-svc"};
  printf("Checking %s\n", names[i]);
  pid_t reader=fork();check(reader>=0,"fork state owner");
  if(!reader){if(peios_token_install(a)<0)_exit(2);int f=open(names[i],O_RDONLY);char data[1024];
   if(f<0||read(f,data,sizeof(data))<=0)_exit(1);
   close(f);_exit(0);}
  check(waitpid(reader,&st,0)==reader&&WIFEXITED(st)&&WEXITSTATUS(st)==0,"owner can read curl state");
  pid_t pid=fork();check(pid>=0,"fork state attacker");if(!pid){if(peios_token_install(b)<0)_exit(2);int f=open(names[i],O_RDONLY);_exit(f<0&&errno==EACCES?0:1);}waitpid(pid,&st,0);check(WIFEXITED(st)&&WEXITSTATUS(st)==0,"other SID cannot read curl state");
 }
 printf("NETWORK_PASS: %u checks\n",checks);reboot(RB_POWER_OFF);return 0;
}

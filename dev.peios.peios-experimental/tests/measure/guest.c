/* SPDX-License-Identifier: MIT
 * Native WHOIS and iperf3 protocol and file-security tests.
 */
#define _GNU_SOURCE
#include <peios/file.h>
#include <peios/security.h>
#include <peios/token.h>
#include <arpa/inet.h>
#include <errno.h>
#include <dirent.h>
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
#include <sys/xattr.h>
#include <unistd.h>
static unsigned checks;
static const void *world_sd; static size_t world_len;
static void check(int ok, const char *why) {
 ++checks; if(ok)return;
 printf("MEASURE_FAIL: %s: %s\n",why,strerror(errno));fflush(NULL);peios_token_revert();reboot(RB_POWER_OFF);_exit(1);
}
static int grant(const char *path,const struct stat *st,int type,struct FTW *f) {
 (void)st;(void)type;(void)f;
 return peios_file_set_sd(AT_FDCWD,path,KACS_SECINFO_DACL,world_sd,world_len,0);
}
static int principal(const char *name, uint64_t privileges) {
 unsigned char sid[PEIOS_SID_MAX_BYTES],world[PEIOS_SID_MAX_BYTES];
 ssize_t n=peios_sid_parse_string(sid,sizeof(sid),name),wn=peios_sid_well_known(world,sizeof(world),PEIOS_WKS_EVERYONE);
 peios_token_builder *b=peios_token_builder_new();check(n>0&&wn>0&&b,"principal builder");
 struct peios_session_spec spec={.logon_type=KACS_LOGON_TYPE_INTERACTIVE,.auth_package="measure-test",.user_sid=sid,.user_sid_len=n};uint64_t id;
 check(!peios_session_create(&spec,&id),"principal session");
 peios_token_builder_privileges(b,privileges,privileges);peios_token_builder_session(b,id);peios_token_builder_user(b,sid,n);peios_token_builder_add_group(b,world,wn,7);
 peios_token_builder_projected_ids(b,1000,1000);peios_token_builder_integrity(b,PEIOS_IL_SYSTEM);
 peios_token_builder_type(b,KACS_TOKEN_TYPE_PRIMARY,KACS_IMLEVEL_IMPERSONATION);
 int fd=peios_token_builder_create(b);peios_token_builder_free(b);check(fd>=0,"principal token");return fd;
}
static void readable(int token, const char *path, int allowed) {
 pid_t pid=fork(); check(pid>=0,"fork access check");
 if(!pid){if(peios_token_install(token)<0)_exit(2);int f=open(path,O_RDONLY);char c;
  if(allowed)_exit(f>=0&&read(f,&c,1)==1?0:1);
  _exit(f<0&&errno==EACCES?0:1);}
 int status;check(waitpid(pid,&status,0)==pid&&WIFEXITED(status)&&WEXITSTATUS(status)==0,allowed?"authorized read":"other SID denied");
}
static pid_t spawn(int token,char *const args[],const char *out) {
 pid_t pid=fork();check(pid>=0,"spawn");
 if(!pid){alarm(20);if(token>=0&&peios_token_install(token)<0)_exit(126);
  int input=open("/dev/null",O_RDONLY);if(input>=0){dup2(input,0);close(input);}
  if(out){int fd=open(out,O_CREAT|O_WRONLY|O_TRUNC,0644);if(fd<0)_exit(125);dup2(fd,1);close(fd);}
  setenv("OPENSSL_CONF","/dev/null",1);setenv("TMPDIR","/work/closed",1);
  execv(args[0],args);perror("exec");_exit(127);}
 return pid;
}
static int reap(pid_t pid) {
 int status;check(waitpid(pid,&status,0)==pid&&WIFEXITED(status),"normal child exit");return WEXITSTATUS(status);
}
static void contents(const char *path,const char *needle,int present) {
 char data[65536];int fd=open(path,O_RDONLY);check(fd>=0,"read result");ssize_t n=read(fd,data,sizeof(data)-1);close(fd);
 check(n>=0,"result data");data[n]=0;check((strstr(data,needle)!=NULL)==present,"result content");
}
static int listen_on(int family,int *port) {
 int fd=socket(family,SOCK_STREAM|SOCK_CLOEXEC,0);check(fd>=0,"fixture socket");
 if(family==AF_INET){struct sockaddr_in a={.sin_family=AF_INET,.sin_addr.s_addr=htonl(INADDR_LOOPBACK)};socklen_t n=sizeof(a);check(!bind(fd,(void*)&a,n)&&!getsockname(fd,(void*)&a,&n),"v4 fixture bind");*port=ntohs(a.sin_port);}
 else {struct sockaddr_in6 a={.sin6_family=AF_INET6,.sin6_addr=IN6ADDR_LOOPBACK_INIT};socklen_t n=sizeof(a);check(!bind(fd,(void*)&a,n)&&!getsockname(fd,(void*)&a,&n),"v6 fixture bind");*port=ntohs(a.sin6_port);}
 check(!listen(fd,4),"fixture listen");return fd;
}
static void whois_check(int token,int family) {
 int port,fd=listen_on(family,&port);pid_t peer=fork();check(peer>=0,"WHOIS peer fork");
 if(!peer){alarm(10);int conn=accept(fd,NULL,NULL);if(conn<0)_exit(1);char buf[128]={0};size_t len=0;
  while(len<sizeof(buf)-1&&!(len>=2&&buf[len-2]=='\r'&&buf[len-1]=='\n')){ssize_t n=read(conn,buf+len,sizeof(buf)-1-len);if(n<=0)_exit(2);len+=n;}
  if(strcmp(buf,"192.0.2.1\r\n"))_exit(3);
  const char reply[]="netname: PEIOS-FIXTURE\r\n";if(write(conn,reply,sizeof(reply)-1)!=sizeof(reply)-1)_exit(4);close(conn);_exit(0);}
 close(fd);char number[16];snprintf(number,sizeof(number),"%d",port);
 char *args[]={"/whois","-h",family==AF_INET?"127.0.0.1":"::1","-p",number,"192.0.2.1",NULL};
 check(reap(spawn(token,args,"/work/whois-output"))==0,"WHOIS client");check(reap(peer)==0,"WHOIS wire query");contents("/work/whois-output","PEIOS-FIXTURE",1);check(!unlink("/work/whois-output"),"WHOIS output cleanup");
}
static void iperf_check(int a,int b,int mode) {
 int port,fd=listen_on(AF_INET,&port);close(fd);char number[16];snprintf(number,sizeof(number),"%d",port);
 char *server[20]={"/iperf3","-s","-1","-p",number,"--pidfile","/work/server.pid"};int si=7;
 if(mode==5){server[si++]="--rsa-private-key-path";server[si++]="/work/auth.key";server[si++]="--authorized-users-path";server[si++]="/work/users";server[si++]="-d";}server[si]=NULL;
 pid_t pid=spawn(-1,server,"/work/server-output");
 struct stat st;int ready=0;for(int i=0;i<200;i++){if(!stat("/work/server.pid",&st)){ready=1;break;}usleep(10000);}check(ready,"server pid ready");readable(b,"/work/server.pid",0);usleep(100000);
 char *client[30]={"/iperf3","-c",mode==4?"::1":"127.0.0.1","-p",number,"-t","1","-b","1M","-J"};int ci=10;
 if(mode==1)client[ci++]="-u";
 if(mode==2||mode==6||mode==7)client[ci++]="-R";
 if(mode==3){client[ci++]="-P";client[ci++]="2";}
 if(mode==4)client[ci++]="-6";
 if(mode==5){client[ci++]="--username";client[ci++]="tester";client[ci++]="--rsa-public-key-path";client[ci++]="/work/auth.pub";}
 if(mode==6||mode==7){client[ci++]="-F";client[ci++]=mode==6?"/work/received":"/work/shared";}
 client[ci]=NULL;
 int result=reap(spawn(a,client,"/work/client-output"));
 if(mode==7){check(result!=0,"shared receive refused");kill(pid,SIGTERM);int status;check(waitpid(pid,&status,0)==pid,"failed transfer server reaped");contents("/work/shared","KEEP",1);}
 else {check(result==0,"iperf client success");check(reap(pid)==0,"iperf server success");contents("/work/client-output","bits_per_second",1);contents("/work/client-output","\"error\"",0);}
 if(mode==5){contents("/work/server-output","fixture-pass",0);contents("/work/server-output","Authentication token decoded",1);}
 if(mode==6){readable(a,"/work/received",1);readable(b,"/work/received",0);}
 check(!unlink("/work/client-output"),"client output cleanup");check(!unlink("/work/server-output"),"server output cleanup");
 if(!access("/work/server.pid",F_OK))check(!unlink("/work/server.pid"),"pid cleanup");
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
 check(!grant("/",NULL,0,NULL)&&!grant("/dev",NULL,0,NULL)&&!grant("/dev/null",NULL,0,NULL),"traversal");
 check(!grant("/dev/urandom",NULL,0,NULL),"random source DACL");
 check(!nftw("/usr",grant,16,FTW_PHYS)&&!nftw("/lib64",grant,16,FTW_PHYS),"runtime DACL");
 check(!grant("/whois",NULL,0,NULL)&&!grant("/iperf3",NULL,0,NULL)&&!grant("/openssl",NULL,0,NULL),"tool DACLs");
 mkdir("/tmp",0777);check(!grant("/tmp",NULL,0,NULL),"tmp DACL");
 check(!mkdir("/work/closed",0700),"closed temporary directory");
 peios_acl_builder *private=peios_acl_builder_new();peios_sd_builder *psd=peios_sd_builder_new();peios_acl_builder_allow(private,system,sn,KACS_ACCESS_GENERIC_ALL,0);ab=peios_acl_builder_bytes(private,&len);peios_sd_builder_dacl(psd,ab,len);peios_sd_builder_control(psd,KACS_SD_DACL_PROTECTED,0);const void *pb=peios_sd_builder_bytes(psd,&len);check(pb&&!peios_file_set_sd(AT_FDCWD,"/work/closed",KACS_SECINFO_DACL,pb,len,0),"closed temporary DACL");
 int ctl=socket(AF_INET,SOCK_DGRAM,0);struct ifreq ifr={0};strcpy(ifr.ifr_name,"lo");check(ctl>=0&&!ioctl(ctl,SIOCGIFFLAGS,&ifr),"loopback flags");ifr.ifr_flags|=IFF_UP;check(!ioctl(ctl,SIOCSIFFLAGS,&ifr),"loopback up");close(ctl);
 int a=principal("S-1-5-21-1188-1",0),b=principal("S-1-5-21-1188-2",0);
 whois_check(a,AF_INET);whois_check(a,AF_INET6);
 char *key[]={"/openssl","genpkey","-algorithm","RSA","-pkeyopt","rsa_keygen_bits:2048","-out","/work/auth.key",NULL};check(reap(spawn(-1,key,NULL))==0,"auth key fixture");
 char *pub[]={"/openssl","pkey","-in","/work/auth.key","-pubout","-out","/work/auth.pub",NULL};check(reap(spawn(-1,pub,NULL))==0,"auth public key");
 const char users[]="tester,66be9990671023646d4b51aaf58ed292b32dffd88e5f6cda5d7fcfbbcbc004b1\n";fd=open("/work/users",O_CREAT|O_WRONLY,0600);check(fd>=0&&write(fd,users,sizeof(users)-1)==sizeof(users)-1,"auth users fixture");close(fd);setenv("IPERF3_PASSWORD","fixture-pass",1);
 fd=open("/work/shared",O_CREAT|O_WRONLY,0600);check(fd>=0&&write(fd,"KEEP",4)==4,"shared receive fixture");close(fd);
 for(int mode=0;mode<8;mode++)iperf_check(a,b,mode);
 char *denied[]={"/iperf3","-s","-1","-p","5201",NULL};check(reap(spawn(a,denied,"/work/denied"))!=0,"ordinary reserved listener refused");
 printf("MEASURE_PASS: %u checks\n",checks);reboot(RB_POWER_OFF);return 0;
}

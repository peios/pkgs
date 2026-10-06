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
 printf("PROBE_FAIL: %s: %s\n",why,strerror(errno));fflush(NULL);peios_token_revert();reboot(RB_POWER_OFF);_exit(1);
}
static int grant(const char *path,const struct stat *st,int type,struct FTW *f) {
 (void)st;(void)type;(void)f;
 return peios_file_set_sd(AT_FDCWD,path,KACS_SECINFO_DACL,world_sd,world_len,0);
}
static int principal(const char *name, uint64_t privileges) {
 unsigned char sid[PEIOS_SID_MAX_BYTES],world[PEIOS_SID_MAX_BYTES];
 ssize_t n=peios_sid_parse_string(sid,sizeof(sid),name),wn=peios_sid_well_known(world,sizeof(world),PEIOS_WKS_EVERYONE);
 peios_token_builder *b=peios_token_builder_new();check(n>0&&wn>0&&b,"principal builder");
 struct peios_session_spec spec={.logon_type=KACS_LOGON_TYPE_INTERACTIVE,.auth_package="probe-test",.user_sid=sid,.user_sid_len=n};uint64_t id;
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
  int input=open(getenv("PROBE_STDIN")?getenv("PROBE_STDIN"):"/dev/null",O_RDONLY);if(input>=0){dup2(input,0);close(input);}
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
int main(int argc, char **argv) {
 if(argc>1 && !strcmp(argv[1],"echo")){puts("PTY-FIXTURE");return 0;}
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
 check(!nftw("/tools",grant,16,FTW_PHYS),"tool DACLs");
 mkdir("/dev/pts",0755);check(!mount("devpts","/dev/pts","devpts",0,"ptmxmode=0666"),"devpts");
 fd=open("/dev/pts",O_PATH|O_DIRECTORY);check(fd>=0&&!peios_mount_set_policy(fd,&policy),"devpts fixture policy");close(fd);
 check(!grant("/dev/ptmx",NULL,0,NULL),"PTY master DACL");
 mkdir("/tmp",0777);check(!grant("/tmp",NULL,0,NULL),"tmp DACL");
 check(!mkdir("/work/closed",0700),"closed temporary directory");
 peios_acl_builder *private=peios_acl_builder_new();peios_sd_builder *psd=peios_sd_builder_new();peios_acl_builder_allow(private,system,sn,KACS_ACCESS_GENERIC_ALL,0);ab=peios_acl_builder_bytes(private,&len);peios_sd_builder_dacl(psd,ab,len);peios_sd_builder_control(psd,KACS_SD_DACL_PROTECTED,0);const void *pb=peios_sd_builder_bytes(psd,&len);check(pb&&!peios_file_set_sd(AT_FDCWD,"/work/closed",KACS_SECINFO_DACL,pb,len,0),"closed temporary DACL");
 int ctl=socket(AF_INET,SOCK_DGRAM,0);struct ifreq ifr={0};strcpy(ifr.ifr_name,"lo");check(ctl>=0&&!ioctl(ctl,SIOCGIFFLAGS,&ifr),"loopback flags");ifr.ifr_flags|=IFF_UP;check(!ioctl(ctl,SIOCSIFFLAGS,&ifr),"loopback up");close(ctl);

 int a=principal("S-1-5-21-1190-1",0),b=principal("S-1-5-21-1190-2",0),raw=principal("S-1-5-21-1190-3",KACS_SE_TCB_PRIVILEGE);
 setenv("PATH","/tools",1);setenv("MTR_PACKET","/tools/mtr-packet",1);setenv("HOME","/work",1);
 char *trace[]={"/tools/traceroute","-n","-m","1","-q","1","-w","1","127.0.0.1",NULL};
 check(reap(spawn(a,trace,"/work/trace"))==0,"ordinary UDP traceroute");contents("/work/trace","127.0.0.1",1);
 char *trace6[]={"/tools/traceroute","-6","-n","-m","1","-q","1","-w","1","::1",NULL};check(reap(spawn(a,trace6,"/work/trace6"))==0,"ordinary IPv6 traceroute");
 char *traw[]={"/tools/traceroute","-I","-n","-m","1","-q","1","-w","1","127.0.0.1",NULL};check(reap(spawn(raw,traw,"/work/traw"))==0,"authorized ICMP traceroute");
 char *mtr[]={"/tools/mtr","-r","-n","-c","1","127.0.0.1",NULL};check(reap(spawn(a,mtr,"/work/mtr-ordinary"))==0,"ordinary MTR report");contents("/work/mtr-ordinary","127.0.0.1",1);check(reap(spawn(raw,mtr,"/work/mtr"))==0,"authorized MTR report");contents("/work/mtr","127.0.0.1",1);
 char *capture_deny[]={"/tools/tcpdump","-i","lo","-c","1",NULL};check(reap(spawn(a,capture_deny,"/work/denied"))!=0,"ordinary capture refused");
 char *pcap_new[]={"/tools/pcap-check","/work/capture","create",NULL};check(reap(spawn(a,pcap_new,NULL))==0,"native pcap create");readable(a,"/work/capture",1);readable(b,"/work/capture",0);
 char *pcap_append[]={"/tools/pcap-check","/work/capture","append",NULL};check(reap(spawn(a,pcap_append,NULL))==0,"native pcap append");
 char *decode[]={"/tools/tcpdump","-nn","-r","/work/capture",NULL};check(reap(spawn(a,decode,"/work/decode"))==0,"offline capture decode");contents("/work/decode","192.0.2.1.1234 > 192.0.2.2.53",1);
 fd=open("/work/shared",O_CREAT|O_WRONLY,0600);check(fd>=0&&write(fd,"KEEP",4)==4,"shared sentinel");close(fd);
 char *pcap_shared[]={"/tools/pcap-check","/work/shared","create",NULL};check(reap(spawn(a,pcap_shared,NULL))!=0,"shared capture refused");contents("/work/shared","KEEP",1);
 check(!symlink("/work/shared","/work/link"),"symlink fixture");char *pcap_link[]={"/tools/pcap-check","/work/link","create",NULL};check(reap(spawn(a,pcap_link,NULL))!=0,"symlink capture refused");contents("/work/shared","KEEP",1);
 check(!mkfifo("/work/fifo",0600),"FIFO fixture");char *pcap_fifo[]={"/tools/pcap-check","/work/fifo","create",NULL};check(reap(spawn(a,pcap_fifo,NULL))!=0,"FIFO capture refused");
 char *dump[]={"/tools/tcpdump","-i","lo","-U","-c","1","-w","/work/live","icmp",NULL};pid_t dumper=spawn(raw,dump,"/work/dump-log");usleep(250000);
 char *ping[]={"/tools/ping","-n","-c","1","-W","1","127.0.0.1",NULL};check(reap(spawn(a,ping,"/work/ping"))==0,"traffic fixture");check(reap(dumper)==0,"live capture");readable(raw,"/work/live",1);readable(b,"/work/live",0);
 int port,listener=listen_on(AF_INET,&port);char porttext[16];snprintf(porttext,sizeof(porttext),"%d",port);
 char *scan[]={"/tools/nmap","--datadir","/usr/share/nmap","-Pn","-n","-p",porttext,"127.0.0.1","-oX","/work/scan",NULL};
 check(reap(spawn(a,scan,"/work/scan-log"))==0,"ordinary Nmap connect scan");readable(a,"/work/scan",1);readable(b,"/work/scan",0);
 /* Inspect private output under the owner token, not SYSTEM. */
 pid_t reader=fork();check(reader>=0,"scan reader");if(!reader){if(peios_token_install(a))_exit(1);contents("/work/scan","type=\"connect\"",1);contents("/work/scan","state=\"open\"",1);_exit(0);}check(reap(reader)==0,"private scan content");
 check(reap(spawn(a,scan,"/work/scan-log"))==0,"private scan overwrite");
 char *scan_raw[]={"/tools/nmap","--datadir","/usr/share/nmap","-Pn","-n","--max-retries","0","-p",porttext,"127.0.0.1","-oX","-",NULL};check(reap(spawn(raw,scan_raw,"/work/raw-scan"))==0,"privileged Nmap scan");contents("/work/raw-scan","type=\"syn\"",1);contents("/work/raw-scan","state=\"open\"",1);
 char *scan_denied[]={"/tools/nmap","-sS","-Pn","-n","-p",porttext,"127.0.0.1",NULL};check(reap(spawn(a,scan_denied,"/work/scan-denied"))!=0,"ordinary SYN scan refused");close(listener);
 char *socat_bad[]={"/tools/socat","-u","OPEN:/work/shared","CREATE:/work/socat-bad,mode=0600",NULL};check(reap(spawn(a,socat_bad,NULL))!=0,"socat permission option refused");check(access("/work/socat-bad",F_OK)<0,"socat rejected before create");
 char *socat_copy[]={"/tools/socat","-u","OPEN:/work/shared","CREATE:/work/relay",NULL};check(reap(spawn(a,socat_copy,NULL))==0,"socat file relay");contents("/work/relay","KEEP",1);

 for(int family=0;family<2;family++) {
  int relayport,sock=listen_on(family?AF_INET6:AF_INET,&relayport);pid_t peer=fork();check(peer>=0,"relay peer");
  if(!peer){alarm(10);int conn=accept(sock,NULL,NULL);if(conn<0)_exit(1);const char msg[]="NETWORK-RELAY";if(write(conn,msg,sizeof(msg)-1)!=(ssize_t)sizeof(msg)-1)_exit(1);close(conn);_exit(0);}close(sock);
  char address[100];snprintf(address,sizeof(address),family?"TCP6:[::1]:%d":"TCP4:127.0.0.1:%d",relayport);
  char *relay[]={"/tools/socat","-u",address,"-",NULL};check(reap(spawn(a,relay,"/work/net-relay"))==0&&reap(peer)==0,"socat network relay");contents("/work/net-relay","NETWORK-RELAY",1);
 }
 char *cert[]={"/tools/openssl","req","-x509","-newkey","rsa:2048","-noenc","-subj","/CN=127.0.0.1","-addext","subjectAltName=IP:127.0.0.1","-days","1","-keyout","/work/tls.key","-out","/work/tls.crt",NULL};check(reap(spawn(-1,cert,"/work/cert-log"))==0,"TLS certificate");
 fd=open("/work/request",O_CREAT|O_WRONLY,0644);const char request[]="GET / HTTP/1.0\r\n\r\n";check(fd>=0&&write(fd,request,sizeof(request)-1)==sizeof(request)-1,"HTTP request");close(fd);
 for(int mismatch=0;mismatch<2;mismatch++) {
  int tlsport,sock=listen_on(AF_INET,&tlsport);close(sock);char number[16],address[256];snprintf(number,sizeof(number),"%d",tlsport);
  char *server[]={"/tools/openssl","s_server","-accept",number,"-cert","/work/tls.crt","-key","/work/tls.key","-www","-naccept","1",NULL};pid_t peer=spawn(-1,server,"/work/tls-server");usleep(250000);
  snprintf(address,sizeof(address),"OPENSSL:127.0.0.1:%d,cafile=/work/tls.crt,commonname=%s",tlsport,mismatch?"wrong.example":"127.0.0.1");
  char *client[]={"/tools/socat","-T","3","-",address,NULL};setenv("PROBE_STDIN","/work/request",1);int rc=reap(spawn(a,client,"/work/tls-client"));unsetenv("PROBE_STDIN");
  check(mismatch?rc!=0:rc==0,mismatch?"TLS hostname mismatch refused":"TLS hostname and CA verified");(void)reap(peer);
  if(!mismatch)contents("/work/tls-client","HTTP/1.0 200",1);
 }
 char *socat_pty[]={"/tools/socat","-u","EXEC:/init echo,pty,raw","-",NULL};check(!grant("/init",NULL,0,NULL),"exec fixture DACL");check(reap(spawn(a,socat_pty,"/work/pty-log"))==0,"socat PTY and exec");contents("/work/pty-log","PTY-FIXTURE",1);
 /* The isolated QEMU user-network gateway answers ARP; no external host is contacted. */
 ctl=socket(AF_INET,SOCK_DGRAM,0);memset(&ifr,0,sizeof(ifr));strcpy(ifr.ifr_name,"eth0");
 struct sockaddr_in *ip=(struct sockaddr_in *)&ifr.ifr_addr;ip->sin_family=AF_INET;inet_pton(AF_INET,"10.0.2.15",&ip->sin_addr);check(!ioctl(ctl,SIOCSIFADDR,&ifr),"ethernet address");
 ip=(struct sockaddr_in *)&ifr.ifr_netmask;ip->sin_family=AF_INET;inet_pton(AF_INET,"255.255.255.0",&ip->sin_addr);check(!ioctl(ctl,SIOCSIFNETMASK,&ifr),"ethernet mask");check(!ioctl(ctl,SIOCGIFFLAGS,&ifr),"ethernet flags");ifr.ifr_flags|=IFF_UP;check(!ioctl(ctl,SIOCSIFFLAGS,&ifr),"ethernet up");close(ctl);
 char *arp[]={"/tools/arping","-I","eth0","-c","1","-w","2","10.0.2.2",NULL};check(reap(spawn(a,arp,"/work/arp-denied"))!=0,"ordinary ARP raw socket refused");check(reap(spawn(raw,arp,"/work/arp"))==0,"authorized ARP reply");contents("/work/arp","Received 1 response",1);
 printf("PROBE_PASS: %u checks\n",checks);reboot(RB_POWER_OFF);return 0;
}

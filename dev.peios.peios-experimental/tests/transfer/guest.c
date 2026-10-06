/* SPDX-License-Identifier: MIT
 * Native rsync destination security and OpenSSL CLI secret-output checks.
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
 printf("TRANSFER_FAIL: %s: %s\n",why,strerror(errno));fflush(NULL);peios_token_revert();reboot(RB_POWER_OFF);_exit(1);
}
static int grant(const char *path,const struct stat *st,int type,struct FTW *f) {
 (void)st;(void)type;(void)f;
 return peios_file_set_sd(AT_FDCWD,path,KACS_SECINFO_DACL,world_sd,world_len,0);
}
static int principal(const char *name, uint64_t privileges) {
 unsigned char sid[PEIOS_SID_MAX_BYTES],world[PEIOS_SID_MAX_BYTES];
 ssize_t n=peios_sid_parse_string(sid,sizeof(sid),name),wn=peios_sid_well_known(world,sizeof(world),PEIOS_WKS_EVERYONE);
 peios_token_builder *b=peios_token_builder_new();check(n>0&&wn>0&&b,"principal builder");
 struct peios_session_spec spec={.logon_type=KACS_LOGON_TYPE_INTERACTIVE,.auth_package="transfer-test",.user_sid=sid,.user_sid_len=n};uint64_t id;
 check(!peios_session_create(&spec,&id),"principal session");
 peios_token_builder_privileges(b,privileges,privileges);peios_token_builder_session(b,id);peios_token_builder_user(b,sid,n);peios_token_builder_add_group(b,world,wn,7);
 peios_token_builder_projected_ids(b,1000,1000);peios_token_builder_integrity(b,PEIOS_IL_SYSTEM);
 peios_token_builder_type(b,KACS_TOKEN_TYPE_PRIMARY,KACS_IMLEVEL_IMPERSONATION);
 int fd=peios_token_builder_create(b);peios_token_builder_free(b);check(fd>=0,"principal token");return fd;
}
static int run(int token,char *const argv[]) {
 pid_t pid=fork();check(pid>=0,"fork command");
 if(!pid){if(token>=0 && peios_token_install(token)<0){perror("install token");_exit(126);}alarm(20); int in=open("/dev/null",O_RDONLY); if(in>=0){dup2(in,0);close(in);} setenv("OPENSSL_CONF","/dev/null",1); execv(argv[0],argv);perror("exec");_exit(127);}
 int status;check(waitpid(pid,&status,0)==pid,"wait command");check(WIFEXITED(status),"command normal exit");return WEXITSTATUS(status);
}
static void readable(int token, const char *path, int allowed) {
 pid_t pid=fork(); check(pid>=0,"fork access check");
 if(!pid){if(peios_token_install(token)<0)_exit(2);int f=open(path,O_RDONLY);char c;
  if(allowed)_exit(f>=0&&read(f,&c,1)==1?0:1);
  _exit(f<0&&errno==EACCES?0:1);}
 int status;check(waitpid(pid,&status,0)==pid&&WIFEXITED(status)&&WEXITSTATUS(status)==0,allowed?"authorized read":"other SID denied");
}
static void assume(int token) {
 int fd=peios_token_duplicate(token,KACS_TOKEN_ALL_ACCESS,KACS_TOKEN_TYPE_IMPERSONATION,KACS_IMLEVEL_IMPERSONATION);
 check(fd>=0&&!peios_token_impersonate(fd),"fixture impersonation");close(fd);
}
static ssize_t descriptor(int token,const char *path,uint32_t all,void *bytes,size_t len) {
 assume(token);ssize_t n=peios_file_get_sd(AT_FDCWD,path,all,bytes,len,0);int saved=errno;
 check(!peios_token_revert(),"fixture revert");errno=saved;return n;
}
static void private_file(int token,const char *path, const char *owner) {
 assume(token);
 unsigned char sid[PEIOS_SID_MAX_BYTES];ssize_t n=peios_sid_parse_string(sid,sizeof(sid),owner);
 peios_acl_builder *a=peios_acl_builder_new();peios_sd_builder *s=peios_sd_builder_new();
 peios_acl_builder_allow(a,sid,n,KACS_ACCESS_GENERIC_ALL,0);size_t al,sl;const void *ab=peios_acl_builder_bytes(a,&al);
 peios_sd_builder_owner(s,sid,n);peios_sd_builder_dacl(s,ab,al);peios_sd_builder_control(s,KACS_SD_DACL_PROTECTED,0);
 const void *sb=peios_sd_builder_bytes(s,&sl);check(sb&&!peios_file_set_sd(AT_FDCWD,path,KACS_SECINFO_OWNER|KACS_SECINFO_DACL,sb,sl,0),"private destination");
 peios_sd_builder_free(s);peios_acl_builder_free(a);check(!peios_token_revert(),"fixture revert");
}
static void owned_link(const char *name,const char *sidtext) {
 check(!symlink("/work/source",name),"fixture symlink creation");
 unsigned char sid[PEIOS_SID_MAX_BYTES];ssize_t n=peios_sid_parse_string(sid,sizeof(sid),sidtext);
 peios_sd_builder *sd=peios_sd_builder_new();check(n>0&&sd,"link owner builder");
 peios_sd_builder_owner(sd,sid,n);size_t len;const void *bytes=peios_sd_builder_bytes(sd,&len);
 check(bytes&&!peios_file_set_sd(AT_FDCWD,name,KACS_SECINFO_OWNER,bytes,len,AT_SYMLINK_NOFOLLOW),"native symlink owner");peios_sd_builder_free(sd);
}
static void interrupted_transfer(int a,int b) {
 check(!mkdir("/work/interrupted",0777),"interruption directory");
 int fd=open("/work/large",O_CREAT|O_WRONLY,0644);check(fd>=0&&!ftruncate(fd,16*1024*1024),"large transfer fixture");close(fd);
 pid_t pid=fork();check(pid>=0,"interruptible transfer fork");
 if(!pid){setpgid(0,0);if(peios_token_install(a)<0)_exit(126);alarm(20);
  execl("/rsync","rsync","--bwlimit=8","--whole-file","/work/large","/work/interrupted/large",NULL);_exit(127);}
 check(!setpgid(pid,pid)||errno==EACCES,"transfer process group");
 char path[1024]={0};
 for(int i=0;i<200&&!path[0];i++){
  DIR *d=opendir("/work/interrupted");check(d!=NULL,"scan staging directory");struct dirent *entry;
  while((entry=readdir(d)))if(!strncmp(entry->d_name,".large.",7))snprintf(path,sizeof(path),"/work/interrupted/%s",entry->d_name);
  closedir(d);if(!path[0])usleep(10000);
 }
 check(path[0]!=0,"private staging visible");readable(b,path,0);
 check(!kill(-pid,SIGKILL),"interrupt transfer group");int status;
 check(waitpid(pid,&status,0)==pid&&WIFSIGNALED(status),"interrupted sender reaped");
 readable(b,path,0);check(!unlink(path),"remove private interrupted stage");
 check(access("/work/interrupted/large",F_OK)<0&&errno==ENOENT,"interruption never published destination");
}
#ifndef SKIP_OPENSSL
static void copy_public(const char *from, const char *to) {
 char bytes[8192];int in=open(from,O_RDONLY),out=open(to,O_WRONLY|O_CREAT|O_TRUNC,0644);ssize_t n;
 check(in>=0&&out>=0,"copy public input");
 while((n=read(in,bytes,sizeof(bytes)))>0)check(write(out,bytes,n)==n,"copy public contents");
 check(n==0,"copy public EOF");close(in);close(out);check(!grant(to,NULL,0,NULL),"public artifact DACL");
}
static void tls_checks(int a,int b) {
 int ctl=socket(AF_INET,SOCK_DGRAM,0);struct ifreq ifr={0};strcpy(ifr.ifr_name,"lo");
 check(ctl>=0&&!ioctl(ctl,SIOCGIFFLAGS,&ifr),"loopback flags");ifr.ifr_flags|=IFF_UP;check(!ioctl(ctl,SIOCSIFFLAGS,&ifr),"loopback up");close(ctl);
 char *serverkey[]={"/openssl","genpkey","-algorithm","ED25519","-out","/work/server.key",NULL};check(run(-1,serverkey)==0,"server fixture key");
 char *req[]={"/openssl","req","-x509","-new","-key","/work/server.key","-subj","/CN=localhost","-addext","subjectAltName=DNS:localhost","-days","1","-out","/work/cert.pem",NULL};
 check(run(-1,req)==0,"TLS fixture certificate");readable(b,"/work/cert.pem",1);
 int sock=socket(AF_INET,SOCK_STREAM,0);struct sockaddr_in address={.sin_family=AF_INET,.sin_addr.s_addr=htonl(INADDR_LOOPBACK)};socklen_t len=sizeof(address);
 check(sock>=0&&!bind(sock,(void*)&address,sizeof(address))&&!getsockname(sock,(void*)&address,&len),"TLS port");close(sock);
 char endpoint[64];snprintf(endpoint,sizeof(endpoint),"127.0.0.1:%u",ntohs(address.sin_port));
 pid_t server=fork();check(server>=0,"TLS server fork");
 if(!server){alarm(30);setenv("OPENSSL_CONF","/dev/null",1);
  int null=open("/dev/null",O_RDWR);if(null>=0){dup2(null,0);dup2(null,1);close(null);}
  execl("/openssl","openssl","s_server","-accept",endpoint,"-cert","/work/cert.pem","-key","/work/server.key","-tls1_2","-www",NULL);_exit(127);}
 int ready=0;
 for(int i=0;i<200;i++){sock=socket(AF_INET,SOCK_STREAM,0);if(sock>=0&&connect(sock,(void*)&address,sizeof(address))==0)ready=1;if(sock>=0)close(sock);if(ready)break;usleep(10000);}
 check(ready,"TLS server ready");
 char *client[]={"/openssl","s_client","-connect",endpoint,"-tls1_2","-brief","-verify_return_error","-verify_hostname","localhost","-CAfile","/work/cert.pem","-keylogfile","/work/keylog","-sess_out","/work/session",NULL};
 check(run(a,client)==0,"strict TLS with private session/keylog");readable(a,"/work/keylog",1);readable(b,"/work/keylog",0);readable(a,"/work/session",1);readable(b,"/work/session",0);
 struct stat before,after;assume(a);check(!stat("/work/keylog",&before),"keylog before append");check(!peios_token_revert(),"fixture revert");
 check(run(a,client)==0,"private keylog append");assume(a);check(!stat("/work/keylog",&after)&&after.st_size>before.st_size,"keylog appended");check(!peios_token_revert(),"fixture revert");
 client[8]="wrong.example";check(run(a,client)!=0,"strict hostname rejection");client[8]="localhost";
 client[12]="/work/shared";check(run(a,client)!=0,"shared keylog refused");client[12]="/work/keylog";
 kill(server,SIGTERM);int status;check(waitpid(server,&status,0)==server,"TLS server reaped");
 check(!mkdir("/etc",0755)&&!mkdir("/etc/ssl",0755)&&!mkdir("/etc/ssl/certs",0755),"trust paths");check(!nftw("/etc",grant,16,FTW_PHYS),"trust path traversal");
 copy_public("/work/cert.pem","/etc/ssl/cert.pem");
 char *verify[]={"/openssl","verify","/work/cert.pem",NULL};check(run(a,verify)==0,"default CAfile trust");
 check(!unlink("/etc/ssl/cert.pem"),"remove default CAfile");check(run(a,verify)!=0,"removed trust fails");
 pid_t hash=fork();check(hash>=0,"hash fixture fork");
 if(!hash){int fd=open("/work/hash",O_WRONLY|O_CREAT|O_TRUNC,0644);if(fd<0)_exit(1);dup2(fd,1);close(fd);setenv("OPENSSL_CONF","/dev/null",1);execl("/openssl","openssl","x509","-in","/work/cert.pem","-subject_hash","-noout",NULL);_exit(127);}
 check(waitpid(hash,&status,0)==hash&&WIFEXITED(status)&&WEXITSTATUS(status)==0,"certificate hash");
 char name[64]={0},path[128];int fd=open("/work/hash",O_RDONLY);ssize_t n=fd<0?-1:read(fd,name,sizeof(name)-1);if(fd>=0)close(fd);check(n==9&&name[8]=='\n',"hash value");name[8]=0;snprintf(path,sizeof(path),"/etc/ssl/certs/%s.0",name);
 copy_public("/work/cert.pem",path);check(run(a,verify)==0,"default hashed CApath trust");
 check(!unlink(path),"remove hashed trust");check(run(a,verify)!=0,"no stale hashed trust");
}

#endif
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
 check(!grant("/",NULL,0,NULL),"root traversal");check(!grant("/dev",NULL,0,NULL)&&!grant("/dev/null",NULL,0,NULL),"null device fixture");
 check(!nftw("/usr",grant,16,FTW_PHYS),"runtime DACL");check(!nftw("/lib64",grant,16,FTW_PHYS),"loader DACL");check(!grant("/rsync",NULL,0,NULL),"rsync DACL");check(!grant("/openssl",NULL,0,NULL),"openssl DACL");

 int a=principal("S-1-5-21-1186-1",0),b=principal("S-1-5-21-1186-2",0);
 int c=principal("S-1-5-21-1186-1",KACS_SE_SECURITY_PRIVILEGE|KACS_SE_RESTORE_PRIVILEGE);

 int f;
#ifndef SKIP_OPENSSL
 char *key[]={"/openssl","genpkey","-algorithm","ED25519","-out","/work/key.pem",NULL};
 check(run(a,key)==0,"private key creation");readable(a,"/work/key.pem",1);readable(b,"/work/key.pem",0);
 check(run(a,key)==0,"private key overwrite");readable(b,"/work/key.pem",0);
 char *random[]={"/openssl","rand","-out","/work/random","32",NULL};
 check(run(a,random)==0,"private random output");readable(a,"/work/random",1);readable(b,"/work/random",0);
 char *derived[]={"/openssl","kdf","-keylen","32","-kdfopt","digest:SHA256","-kdfopt","hexkey:1234","-out","/work/derived","HKDF",NULL};
 check(run(a,derived)==0,"private KDF output");readable(b,"/work/derived",0);
 char *store[]={"/openssl","storeutl","-keys","-out","/work/export.pem","/work/key.pem",NULL};
 check(run(a,store)==0,"private mixed export");readable(b,"/work/export.pem",0);
 f=open("/work/shared",O_CREAT|O_WRONLY,0600);check(f>=0&&write(f,"keep",4)==4,"shared target fixture");close(f);
 char *unsafe[]={"/openssl","rand","-out","/work/shared","32",NULL};
 check(run(a,unsafe)!=0,"shared secret target refused");
 char data[8]={0};f=open("/work/shared",O_RDONLY);check(f>=0&&read(f,data,8)==4&&!memcmp(data,"keep",4),"shared target unchanged");close(f);
 check(!symlink("/work/key.pem","/work/link"),"secret symlink fixture");
 unsafe[3]="/work/link";check(run(a,unsafe)!=0,"secret symlink refused");
 assume(a);check(!link("/work/key.pem","/work/key-hardlink"),"secret hardlink fixture");check(!peios_token_revert(),"fixture revert");
 check(run(a,key)!=0,"multiply linked secret refused");check(!unlink("/work/key-hardlink"),"remove fixture hardlink");
 check(!mkfifo("/work/fifo",0666),"secret FIFO fixture");
 unsafe[3]="/work/fifo";check(run(a,unsafe)!=0,"secret FIFO refused without blocking");
 unsafe[3]="/dev/null";check(run(a,unsafe)!=0,"named secret device refused");
 char *converted[]={"/openssl","pkey","-in","/work/key.pem","-out","/work/converted.pem",NULL};
 check(run(a,converted)==0,"private key conversion");readable(b,"/work/converted.pem",0);
 char *encrypt[]={"/openssl","enc","-aes-256-cbc","-pbkdf2","-pass","pass:fixture-only","-in","/work/shared","-out","/work/encrypted",NULL};
 check(run(a,encrypt)==0,"encryption fixture");
 char *decrypt[]={"/openssl","enc","-d","-aes-256-cbc","-pbkdf2","-pass","pass:fixture-only","-in","/work/encrypted","-out","/work/plaintext",NULL};
 check(run(a,decrypt)==0,"private decrypted plaintext");readable(b,"/work/plaintext",0);
 char *cmsenc[]={"/openssl","cms","-EncryptedData_encrypt","-aes-128-cbc","-secretkey","000102030405060708090a0b0c0d0e0f","-in","/work/shared","-out","/work/cms-encrypted",NULL};
 check(run(a,cmsenc)==0,"CMS encryption fixture");
 char *cmsdec[]={"/openssl","cms","-EncryptedData_decrypt","-secretkey","000102030405060708090a0b0c0d0e0f","-in","/work/cms-encrypted","-out","/work/cms-plaintext",NULL};
 check(run(a,cmsdec)==0,"private CMS decrypted plaintext");readable(a,"/work/cms-plaintext",1);readable(b,"/work/cms-plaintext",0);
 char *seed[]={"/openssl","rand","-hex","-writerand","/work/seed","1",NULL};
 check(run(a,seed)==0,"private seed output");readable(b,"/work/seed",0);
 tls_checks(a,b);

#endif
 check(!mkdir("/work/source",0777)&&!mkdir("/work/dest",0777),"transfer directories");
 f=open("/work/source/file",O_CREAT|O_WRONLY,0666);check(f>=0&&write(f,"content",7)==7,"transfer input");close(f);
 char *copy[]={"/rsync","-rlt","/work/source/","/work/dest/",NULL};
 check(run(a,copy)==0,"native new transfer");readable(a,"/work/dest/file",1);readable(b,"/work/dest/file",1);
 private_file(c,"/work/dest/file","S-1-5-21-1186-1");
 unsigned char before[65535],after[65535];uint32_t all=KACS_SECINFO_OWNER|KACS_SECINFO_GROUP|KACS_SECINFO_DACL|KACS_SECINFO_SACL;
 ssize_t n=descriptor(c,"/work/dest/file",all,before,sizeof(before));check(n>0,"snapshot destination security");
 char *update[]={"/rsync","-rlt","--ignore-times","/work/source/","/work/dest/",NULL};
 check(run(a,update)!=0,"unauthorized full-security replacement refused");
 char *inplace[]={"/rsync","-rlt","--ignore-times","--inplace","/work/source/","/work/dest/",NULL};
 check(run(a,inplace)==0,"explicit in-place update");readable(b,"/work/dest/file",0);
 check(descriptor(c,"/work/dest/file",all,after,sizeof(after))==n&&!memcmp(before,after,n),"in-place preserves security");
 check(run(c,update)==0,"authorized replacement");
 check(descriptor(c,"/work/dest/file",all,after,sizeof(after))==n&&!memcmp(before,after,n),"replacement preserves full security");readable(b,"/work/dest/file",0);
 check(!setxattr("/work/source/file","user.transfer-test","value",5,0),"data xattr fixture");
 char *xcopy[]={"/rsync","-rltX","--ignore-times","--inplace","/work/source/","/work/dest/",NULL};
 check(run(a,xcopy)==0,"data xattr transfer");
 assume(a);char attr[16];check(getxattr("/work/dest/file","user.transfer-test",attr,sizeof(attr))==5&&!memcmp(attr,"value",5),"data xattr retained");check(!peios_token_revert(),"fixture revert");
 check(descriptor(c,"/work/dest/file",all,after,sizeof(after))==n&&!memcmp(before,after,n),"xattrs preserve native security");
 char *archive[]={"/rsync","-a","/work/source/","/work/dest/",NULL};check(run(a,archive)!=0,"archive preservation rejected");
 char *daemon[]={"/rsync","--daemon","--no-detach",NULL};check(run(a,daemon)!=0,"daemon serving rejected");
 owned_link("/work/foreign-link","S-1-5-21-1186-2");
 struct stat linkstat;check(!lstat("/work/foreign-link",&linkstat)&&linkstat.st_uid==0,"cosmetic uid-zero symlink");
 char *linkcopy[]={"/rsync","/work/shared","/work/foreign-link/copied",NULL};
 check(run(a,linkcopy)!=0,"foreign SID uid-zero symlink refused");
 owned_link("/work/own-link","S-1-5-21-1186-1");
 linkcopy[2]="/work/own-link/copied";
 check(run(a,linkcopy)==0,"own SID symlink accepted");
 interrupted_transfer(a,b);
 printf("TRANSFER_PASS: %u checks\n",checks);reboot(RB_POWER_OFF);return 0;
}

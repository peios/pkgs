/* SPDX-License-Identifier: MIT */
#include <pcap/pcap.h>
#include <stdio.h>
#include <string.h>
int main(int argc,char **argv) {
 if(argc!=3)return 2;
 pcap_t *p=pcap_open_dead(DLT_EN10MB,65535);if(!p)return 2;
 pcap_dumper_t *d=!strcmp(argv[2],"append")?pcap_dump_open_append(p,argv[1]):pcap_dump_open(p,argv[1]);
 if(!d){fprintf(stderr,"pcap fixture: %s\n",pcap_geterr(p));pcap_close(p);return 1;}
 const unsigned char packet[]={0xff,0xff,0xff,0xff,0xff,0xff,2,0,0,0,0,1,8,0,0x45,0,0,28,0,1,0,0,64,17,0,0,192,0,2,1,192,0,2,2,4,210,0,53,0,8,0,0};
 struct pcap_pkthdr h={.ts={0,0},.caplen=sizeof(packet),.len=sizeof(packet)};pcap_dump((unsigned char*)d,&h,packet);
 int result=pcap_dump_flush(d);pcap_dump_close(d);pcap_close(p);return result?1:0;
}

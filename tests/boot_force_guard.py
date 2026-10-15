"""Exercise all skip/force combinations from the patched initramfs source."""
import subprocess


def force_guard(source,folder):
    text=source.read_text()
    begin=text.index('\tif (do_skip_initramfs && !IS_ENABLED(CONFIG_INITRAMFS_FORCE))')
    end=text.index('\t/* If available load the bootloader supplied initrd */',begin)
    body=text[begin:end]
    harness=r'''#include <stdlib.h>
#define IS_ENABLED(x) (x)
#define CONFIG_INITRAMFS_FORCE force_builtin
static int force_builtin,do_skip_initramfs,initrd_start=1;
static int freed,builtin,defaults;
static char __initramfs_start[1];
static unsigned long __initramfs_size=1;
static void free_initrd(void){freed++;}
static int default_rootfs(void){defaults++;return 17;}
static char *unpack_to_rootfs(char *data,unsigned long size){if(data!=__initramfs_start||size!=1)abort();builtin++;return 0;}
static void panic(char *format,char *error){abort();}
static int populate(void){char *err;
'''+body+r'''
return 7;}
int main(void){
 for(force_builtin=0;force_builtin<2;force_builtin++){
  for(do_skip_initramfs=0;do_skip_initramfs<2;do_skip_initramfs++){
   freed=builtin=defaults=0;
   int got=populate();
   if(do_skip_initramfs&&!force_builtin){if(got!=17||freed!=1||defaults!=1||builtin)abort();}
   else {if(got!=7||freed||defaults||builtin!=1)abort();}
  }
 }
 return 0;
}
'''
    path=folder/'force.c';path.write_text(harness)
    subprocess.run(['cc','-std=c11','-Werror',str(path),'-o',str(folder/'force-test')],check=True)
    subprocess.run([str(folder/'force-test')],check=True)

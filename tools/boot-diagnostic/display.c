/* Minimal fbdev diagnostic; never opens storage, /dev/mem, a shell or network. */
#include <errno.h>
#include <fcntl.h>
#include <linux/fb.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

/* Original 5 by 7 uppercase glyphs: one five-bit row per byte. */
static const struct { char c; unsigned char row[7]; } font[] = {
 {'A',{14,17,17,31,17,17,17}}, {'B',{30,17,17,30,17,17,30}},
 {'C',{14,17,16,16,16,17,14}}, {'D',{30,17,17,17,17,17,30}},
 {'E',{31,16,16,30,16,16,31}}, {'F',{31,16,16,30,16,16,16}},
 {'G',{14,17,16,23,17,17,15}}, {'H',{17,17,17,31,17,17,17}},
 {'I',{31,4,4,4,4,4,31}}, {'J',{7,2,2,2,2,18,12}},
 {'K',{17,18,20,24,20,18,17}}, {'L',{16,16,16,16,16,16,31}},
 {'M',{17,27,21,21,17,17,17}}, {'N',{17,25,21,19,17,17,17}},
 {'O',{14,17,17,17,17,17,14}}, {'P',{30,17,17,30,16,16,16}},
 {'Q',{14,17,17,17,21,18,13}}, {'R',{30,17,17,30,20,18,17}},
 {'S',{15,16,16,14,1,1,30}}, {'T',{31,4,4,4,4,4,4}},
 {'U',{17,17,17,17,17,17,14}}, {'V',{17,17,17,17,17,10,4}},
 {'W',{17,17,17,21,21,21,10}}, {'X',{17,17,10,4,10,17,17}},
 {'Y',{17,17,10,4,4,4,4}}, {'Z',{31,1,2,4,8,16,31}},
 {'0',{14,17,19,21,25,17,14}}, {'1',{4,12,4,4,4,4,14}},
 {'2',{14,17,1,2,4,8,31}}, {'3',{30,1,1,14,1,1,30}},
 {'4',{2,6,10,18,31,2,2}}, {'5',{31,16,16,30,1,1,30}},
 {'6',{14,16,16,30,17,17,14}}, {'7',{31,1,2,4,8,8,8}},
 {'8',{14,17,17,14,17,17,14}}, {'9',{14,17,17,15,1,1,14}},
 {':',{0,4,4,0,4,4,0}}, {'-',{0,0,0,31,0,0,0}},
 {'+',{0,4,4,31,4,4,0}}
};

static int layout(const struct fb_var_screeninfo *v,
                  const struct fb_fix_screeninfo *f, size_t *length) {
    if (!v->xres || v->xres > 4096 || !v->yres || v->yres > 4096 ||
        v->bits_per_pixel != 32 || v->xres_virtual < v->xres ||
        v->yres_virtual < v->yres || f->type != FB_TYPE_PACKED_PIXELS ||
        f->visual != FB_VISUAL_TRUECOLOR || f->line_length < v->xres * 4 ||
        f->line_length > 32768 || f->smem_len > 64U * 1024U * 1024U ||
        v->red.length != 8 || v->green.length != 8 || v->blue.length != 8 ||
        v->red.offset > 24 || v->green.offset > 24 || v->blue.offset > 24 ||
        v->red.msb_right || v->green.msb_right || v->blue.msb_right ||
        (v->transp.length && (v->transp.length != 8 || v->transp.offset > 24 || v->transp.msb_right)))
        return -1;
    uint32_t r = 255U << v->red.offset, g = 255U << v->green.offset,
             b = 255U << v->blue.offset;
    if ((r & g) || (r & b) || (g & b) ||
        (v->transp.length && ((255U << v->transp.offset) & (r | g | b))))
        return -1;
    *length = (size_t)f->line_length * v->yres;
    return *length <= f->smem_len ? 0 : -1;
}

static uint32_t pixel(const struct fb_var_screeninfo *v,
                      unsigned r, unsigned g, unsigned b) {
    return (r << v->red.offset) | (g << v->green.offset) | (b << v->blue.offset) |
           (v->transp.length ? 255U << v->transp.offset : 0);
}

static void render(unsigned char *map, const struct fb_var_screeninfo *v,
                   const struct fb_fix_screeninfo *f, int count, char **lines) {
    unsigned scale = v->xres / 200;
    if (!scale) scale = 1;
    if (scale > 8) scale = 8;
    uint32_t bg = pixel(v, 12, 30, 46), fg = pixel(v, 235, 245, 250);
    for (unsigned y = 0; y < v->yres; ++y)
        for (unsigned x = 0; x < v->xres; ++x)
            memcpy(map + (size_t)y * f->line_length + x * 4, &bg, 4);
    for (int line = 0; line < count && line < 12; ++line) {
        unsigned y0 = 12 * scale + (unsigned)line * 12 * scale;
        for (unsigned ch = 0; lines[line][ch] && ch < 32; ++ch) {
            unsigned x0 = 6 * scale + ch * 6 * scale;
            for (unsigned k = 0; k < sizeof(font) / sizeof(font[0]); ++k) {
                if (font[k].c != lines[line][ch]) continue;
                for (unsigned row = 0; row < 7; ++row)
                    for (unsigned col = 0; col < 5; ++col)
                        if (font[k].row[row] & (1U << (4 - col)))
                            for (unsigned dy = 0; dy < scale; ++dy)
                                for (unsigned dx = 0; dx < scale; ++dx) {
                                    unsigned x = x0 + col * scale + dx;
                                    unsigned y = y0 + row * scale + dy;
                                    if (x < v->xres && y < v->yres)
                                        memcpy(map + (size_t)y * f->line_length + x * 4, &fg, 4);
                                }
                break;
            }
        }
    }
}

static int self_test(void) {
    struct fb_var_screeninfo v = {.xres=1440,.yres=3040,.xres_virtual=1440,
        .yres_virtual=6080,.bits_per_pixel=32,.red={16,8,0},.green={8,8,0},
        .blue={0,8,0},.transp={24,8,0}};
    struct fb_fix_screeninfo f = {.type=FB_TYPE_PACKED_PIXELS,
        .visual=FB_VISUAL_TRUECOLOR,.line_length=5760,.smem_len=35020800};
    size_t length;
    if (layout(&v,&f,&length) || length != 17510400) return 90;
    unsigned char *m = malloc(length + 16);
    if (!m) return 91;
    memset(m + length,0xA5,16);
    char *lines[] = {"UBUNTU TOUCH TEST 1","KERNEL: RUNNING","RAMDISK: RUNNING",
        "DATA: LOG SAVED","SYSTEM: READABLE","VENDOR: READABLE",
        "USB: CONFIGURED","WAIT 60 SECONDS","THEN RETURN TO TWRP"};
    render(m,&v,&f,9,lines);
    for (size_t i=0;i<16;++i) if (m[length+i]!=0xA5) return 92;
    /* Exact BGRA pixel and an actual lit glyph pixel. */
    if (memcmp(m,"\x2e\x1e\x0c\xff",4) ||
        memcmp(m+(size_t)84*f.line_length+42*4,"\xfa\xf5\xeb\xff",4)) return 93;
    free(m);
    f.smem_len=length-1; if (!layout(&v,&f,&length)) return 94;
    f.smem_len=35020800;v.bits_per_pixel=16;if (!layout(&v,&f,&length)) return 95;
    v.bits_per_pixel=32;v.red.offset=0;if (!layout(&v,&f,&length)) return 96;
    puts("PASS: bounded BGRA framebuffer rendering; no device accessed");
    return 0;
}

int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1],"--self-test")) return self_test();
    if (argc < 2 || argc > 13) return 2;
    int fd = open("/dev/fb0",O_RDWR | O_CLOEXEC);
    if (fd < 0) { perror("fb0 open"); return 3; }
    struct fb_var_screeninfo v;
    struct fb_fix_screeninfo f;
    size_t length;
    if (ioctl(fd,FBIOGET_VSCREENINFO,&v) || ioctl(fd,FBIOGET_FSCREENINFO,&f) ||
        layout(&v,&f,&length)) { fprintf(stderr,"fb0 layout unsupported or unavailable\n");close(fd);return 4; }
    printf("fb0: %u x %u, stride %u, mapped bytes %zu\n",v.xres,v.yres,f.line_length,length);
    fflush(stdout);
    unsigned char *map = mmap(NULL,length,PROT_READ | PROT_WRITE,MAP_SHARED,fd,0);
    if (map == MAP_FAILED) { perror("fb0 mmap"); close(fd); return 5; }
    if (ioctl(fd,FBIOBLANK,FB_BLANK_UNBLANK)) perror("fb0 unblank");
    render(map,&v,&f,argc-1,argv+1);
    v.xoffset=0;v.yoffset=0;v.activate=FB_ACTIVATE_VBL;
    int result=ioctl(fd,FBIOPAN_DISPLAY,&v);
    if (result) perror("fb0 present"); else puts("fb0 diagnostic submitted");
    munmap(map,length);close(fd);
    return result ? 6 : 0;
}

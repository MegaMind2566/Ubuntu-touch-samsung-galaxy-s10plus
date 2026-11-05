#!/usr/bin/env python3
"""Compile exact source methods against Linux I/O boundaries, without USB hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


def body(source, name):
    match = re.search(r"\bvoid\s+" + re.escape(name) + r"\(\)[^;{}]*\{", source)
    if not match:
        raise ValueError(f"method definition missing: {name}")
    start = match.end() - 1
    depth = 1
    end = start + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


COMMON = r'''
#include <array>
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstring>
#include <endian.h>
#include <fcntl.h>
#include <iostream>
#include <memory>
#include <mutex>
#include <poll.h>
#include <string>
#include <sys/eventfd.h>
#include <sys/stat.h>
#include <thread>
#include <unistd.h>
#include <linux/usb/ch9.h>
#include <linux/usb/functionfs.h>
using namespace std::chrono_literals;
struct Log {
    const char* level;
    template<class T> Log& operator<<(const T&) { return *this; }
    ~Log() { if (!strcmp(level, "FATAL")) abort(); }
};
#define LOG(level) Log{#level}
#define PLOG(level) LOG(level)
#define CHECK(x) do { if (!(x)) { std::cerr << "check failed: " #x "\n"; abort(); } } while (0)
#define CHECK_EQ(a,b) CHECK((a)==(b))
namespace android { namespace base {
class unique_fd {
    int fd_ = -1;
  public:
    unique_fd() = default;
    explicit unique_fd(int fd) : fd_(fd) {}
    unique_fd(const unique_fd&) = delete;
    unique_fd(unique_fd&& other) : fd_(other.release()) {}
    unique_fd& operator=(unique_fd&& other) { reset(other.release()); return *this; }
    ~unique_fd() { reset(); }
    int get() const { return fd_; }
    int release() { int result=fd_; fd_=-1; return result; }
    void reset(int fd=-1) { if(fd_>=0) close(fd_); fd_=fd; }
    bool operator<(int n) const { return fd_<n; }
    bool operator==(int n) const { return fd_==n; }
};
inline bool SetProperty(const char*, const char*) { return true; }
}}
using android::base::unique_fd;
inline ssize_t adb_read(int fd, void* data, size_t n) {
    ssize_t result; do { result=read(fd,data,n); } while(result<0 && errno==EINTR);
    return result;
}
inline ssize_t adb_write(int fd, const void* data, size_t n) { return write(fd,data,n); }
'''

PROTOCOL = r'''
using adb_pollfd = pollfd;
inline int adb_poll(pollfd* fds, size_t n, int timeout) { return poll(fds,n,timeout); }
inline void adb_thread_setname(const char*) {}
inline const char* to_string(usb_functionfs_event_type) { return "fixture event"; }
constexpr int kInterruptionSignal=SIGUSR1;
constexpr size_t kUsbReadQueueDepth=8;
struct UsbFfsControl { unique_fd fd; bool bound=false, enabled=false; };
struct Fixture {
    std::shared_ptr<UsbFfsControl> control_;
    unique_fd control_fd_; // Used only by unmodified baseline method.
    unique_fd worker_event_fd_{eventfd(0,EFD_CLOEXEC)};
    unique_fd monitor_event_fd_{eventfd(0,EFD_CLOEXEC)};
    std::thread monitor_thread_, worker_thread_;
    bool worker_started_=false;
    std::atomic<bool> stopped_{false}, worker_exited_{false}, completed{false};
    std::atomic<int> submitted{0};
    std::mutex write_mutex_;
    std::array<int,kUsbReadQueueDepth> read_requests_{};
    int next_read_id_=0, behavior;
    explicit Fixture(std::shared_ptr<UsbFfsControl> c, int b)
        : control_(c), control_fd_(dup(c->fd.get())), behavior(b) {}
    ~Fixture() { Stop(); if(monitor_thread_.joinable()) monitor_thread_.join(); }
    int CreateReadBlock(int id) { return id; }
    bool SubmitRead(int*) {
        ++submitted;
        if(behavior==1) return false; // Actual worker's early return path.
        if(behavior==2) {
            // External io_submit boundary: interruptible blocking wait.
            pollfd pfd{worker_event_fd_.get(),POLLIN,0};
            int result=poll(&pfd,1,-1);
            CHECK(result>=0 || errno==EINTR);
            return false;
        }
        return true;
    }
    void ReadEvents() {}
    void SubmitWrites() {}
    void HandleError(const std::string&) { Stop(); completed=true; }
    // EXACT_METHODS
};
template<class Predicate> void wait_for(Predicate predicate) {
    auto deadline=std::chrono::steady_clock::now()+10s;
    while(!predicate()) {
        CHECK(std::chrono::steady_clock::now()<deadline);
        std::this_thread::sleep_for(1ms);
    }
}
void send_event(int fd, usb_functionfs_event_type type) {
    usb_functionfs_event event{}; event.type=type;
    CHECK_EQ(write(fd,&event,sizeof(event)),ssize_t(sizeof(event)));
}
int main(int argc, char** argv) {
    CHECK(argc==2);
    int endpoints[2]; CHECK_EQ(pipe(endpoints),0);
    auto control=std::make_shared<UsbFfsControl>(); control->fd.reset(endpoints[0]);
    unique_fd writer(endpoints[1]);
    std::string test=argv[1];
    int behavior=test=="early"?1:test=="interrupt"?2:0;
    int rounds=test=="retained"?3:1;
    if(test=="stopped-enabled" || test=="pending-disable") {
        { Fixture f(control,0); f.StartMonitor();
          send_event(writer.get(),FUNCTIONFS_BIND);
          send_event(writer.get(),FUNCTIONFS_ENABLE);
          wait_for([&] { return f.submitted.load()==8; });
          f.Stop(); wait_for([&] { return f.completed.load(); }); }
        CHECK(control->enabled);
        if(test=="pending-disable") {
            send_event(writer.get(),FUNCTIONFS_DISABLE);
            { Fixture f(control,0); f.StartMonitor();
              wait_for([&] { return f.completed.load(); });
              CHECK_EQ(f.submitted.load(),0); }
            CHECK(!control->enabled);
        }
        { Fixture f(control,0); f.StartMonitor();
          if(test=="pending-disable") send_event(writer.get(),FUNCTIONFS_ENABLE);
          wait_for([&] { return f.submitted.load()==8; });
          send_event(writer.get(),FUNCTIONFS_DISABLE);
          wait_for([&] { return f.completed.load(); }); }
        std::cout << test << ": completed\n";
        return 0;
    }
    for(int i=0;i<rounds;++i) {
        Fixture f(control,behavior); f.StartMonitor();
        if(i==0) send_event(writer.get(),FUNCTIONFS_BIND);
        send_event(writer.get(),FUNCTIONFS_ENABLE);
        wait_for([&] { return f.submitted.load()>0; });
        if(behavior==0) wait_for([&] { return f.submitted.load()==8; });
        send_event(writer.get(),FUNCTIONFS_DISABLE);
        wait_for([&] { return f.completed.load(); });
    }
    if(test=="unbind") {
        { Fixture f(control,0); f.StartMonitor();
          send_event(writer.get(),FUNCTIONFS_UNBIND);
          wait_for([&] { return f.completed.load(); }); }
        CHECK(!control->bound);
        { Fixture f(control,0); f.StartMonitor();
          send_event(writer.get(),FUNCTIONFS_BIND);
          send_event(writer.get(),FUNCTIONFS_ENABLE);
          wait_for([&] { return f.submitted.load()==8; });
          send_event(writer.get(),FUNCTIONFS_DISABLE);
          wait_for([&] { return f.completed.load(); }); }
    }
    std::cout << test << ": completed\n";
}
'''

FFS_PREFIX = r'''
std::string ep0, ep1, ep2;
int control_opens=0;
#define USB_FFS_ADB_EP0 ep0.c_str()
#define USB_FFS_ADB_OUT ep1.c_str()
#define USB_FFS_ADB_IN ep2.c_str()
#define ADB_CLASS 255
#define ADB_SUBCLASS 66
#define ADB_PROTOCOL 1
#define MAX_PAYLOAD (1024*1024)
#define D(...) do {} while(0)
inline int adb_open(const char* path, int flags) {
    if(path==ep0) ++control_opens;
    return open(path,flags);
}
'''

FFS_MAIN = r'''
int main(int argc,char** argv) {
    CHECK(argc==2);
    ep0=std::string(argv[1])+"/ep0"; ep1=std::string(argv[1])+"/ep1";
    ep2=std::string(argv[1])+"/ep2";
    for(auto& path:{ep0,ep1,ep2}) { unique_fd f(open(path.c_str(),O_CREAT|O_RDWR,0600)); CHECK(f.get()>=0); }
    unique_fd control,out,in;
    CHECK(open_functionfs(&control,&out,&in));
    int original=control.get(); CHECK(original>=0);
    struct stat before{},after{}; CHECK_EQ(fstat(original,&before),0);
    off_t descriptor_end=lseek(original,0,SEEK_CUR); CHECK(descriptor_end>0);
    out.reset(); in.reset();
    CHECK(open_functionfs(&control,&out,&in));
    CHECK_EQ(control.get(),original);
    CHECK_EQ(fstat(control.get(),&after),0);
    CHECK_EQ(before.st_ino,after.st_ino);
    CHECK_EQ(lseek(control.get(),0,SEEK_CUR),descriptor_end);
    CHECK_EQ(control_opens,1);
    std::cout << "control fd retained; descriptors written only once\n";
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--expect", choices=("baseline", "candidate"), required=True)
    parser.add_argument("--cxx", default="clang++")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(Path(__file__).with_name("candidate.json").read_text())
    patch = Path(__file__).with_name("0001-adbd-functionfs-reconnect.patch")
    if hashlib.sha256(patch.read_bytes()).hexdigest() != manifest["patch_sha256"]:
        raise ValueError("candidate patch hash mismatch")
    expected = manifest["source_before_sha256" if args.expect == "baseline" else "source_after_sha256"]
    source = {}
    for name, digest in expected.items():
        data = (args.source / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"source hash mismatch: {name}")
        source[name] = data.decode()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    methods = "\n".join(f"void {name}() " + body(source["daemon/usb.cpp"], name)
                        for name in ("Stop", "StartMonitor", "StartWorker", "StopWorker"))
    protocol = COMMON + PROTOCOL.replace("// EXACT_METHODS", methods)
    ffs = COMMON + FFS_PREFIX + "\n".join(
        line for line in source["daemon/usb_ffs.cpp"].splitlines()
        if not line.startswith("#include")) + FFS_MAIN
    results = {"source": expected, "expectation": args.expect, "cases": {}}
    for name, text in (("protocol", protocol), ("ffs", ffs)):
        cpp, binary = args.output / (name + ".cpp"), args.output / name
        cpp.write_text(text, encoding="utf-8")
        subprocess.run([args.cxx, "-std=c++20", "-pthread", "-O2", str(cpp), "-o", str(binary)], check=True, timeout=60)
    cases = ["early", "idle", "interrupt", "retained", "unbind", "stopped-enabled", "pending-disable"] if args.expect == "candidate" else ["early"]
    for name in cases + ["ffs"]:
        command = [str(args.output / ("ffs" if name == "ffs" else "protocol")),
                   str(args.output) if name == "ffs" else name]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=3)
            observed = "pass" if result.returncode == 0 else "failed"
            detail = result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            observed, detail = "timeout", "child killed and reaped by subprocess.run"
        required = "pass" if args.expect == "candidate" else ("failed" if name == "ffs" else "timeout")
        results["cases"][name] = {"observed": observed, "required": required, "detail": detail}
        print(f"{args.expect}: {name}: {observed} (required {required})", flush=True)
    (args.output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    return 0 if all(c["observed"] == c["required"] for c in results["cases"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())

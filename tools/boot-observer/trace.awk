# A regular file retains shell fragments that /dev/kmsg did not retain in BOOT 3.
# Keep draining the pipe after the cap so PID 1 never gets a broken pipe.
BEGIN { bytes = 0; limit = 4194304; capped = 0 }
{
    size = length($0) + 1
    if (!capped && bytes + size <= limit - 64) {
        print $0
        bytes += size
        fflush()
    } else if (!capped) {
        print "UT_BOOT_5: trace limit reached; remaining output discarded"
        capped = 1
        fflush()
    }
}

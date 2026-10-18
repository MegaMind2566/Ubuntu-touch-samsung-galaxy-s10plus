"""Model root-owned TWRP userdata in a host-owned temporary test directory."""
import os
from pathlib import Path
import shlex


def root_owned_stat_bridge(backend, data, owner=None):
    """Translate only this fixture owner's UID/GID pair in terse stat output.

    All other metadata and foreign owners remain unchanged. The production
    ownership checks still consume and validate the resulting stat records.
    """
    uid, gid = owner if owner is not None else (os.getuid(), os.getgid())
    root = shlex.quote(str(Path(data)))
    command = backend + ' "$@"' if backend else '"$@"'
    return ('if [ "$1" = stat ] && [ "$2" = -t ]; then\n'
            '    case "$3" in ' + root + '|' + root + '/*)\n'
            '        metadata=$(' + command + ') || exit $?\n'
            '        set -- $metadata\n'
            '        [ "$#" -ge 6 ] || exit 1\n'
            '        printf "%s %s %s %s" "$1" "$2" "$3" "$4"\n'
            '        if [ "$5" = ' + str(uid) + ' ] && [ "$6" = ' + str(gid) + ' ]; then\n'
            '            printf " 0 0"\n'
            '        else\n'
            '            printf " %s %s" "$5" "$6"\n'
            '        fi\n'
            '        shift 6\n'
            '        if [ "$#" -gt 0 ]; then printf " %s" "$@"; fi\n'
            '        printf "\\n"\n'
            '        exit 0 ;;\n'
            '    esac\n'
            'fi\n')


def stat_reader_with_owner(path, backend, uid, gid):
    """Create a stat-only fixture backend for a simulated nonroot runner."""
    path = Path(path)
    command = backend + ' "$@"' if backend else '"$@"'
    path.write_text('#!/bin/sh\n'
                    'metadata=$(' + command + ') || exit $?\n'
                    'set -- $metadata\n'
                    '[ "$#" -ge 6 ] || exit 1\n'
                    'printf "%s %s %s %s ' + str(uid) + ' ' + str(gid) + '" "$1" "$2" "$3" "$4"\n'
                    'shift 6\n'
                    'if [ "$#" -gt 0 ]; then printf " %s" "$@"; fi\n'
                    'printf "\\n"\n')
    path.chmod(0o700)
    return shlex.quote(str(path))

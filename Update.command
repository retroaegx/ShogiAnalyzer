#!/bin/sh
main() {
    here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || return 1
    if [ -f "$here/.UpdateRecovery.sh" ]; then
        sh "$here/.UpdateRecovery.sh"
        return $?
    fi
    if [ -x "$here/ShogiAnalyzer" ]; then
        job=$(mktemp -d "${TMPDIR:-/tmp}/ShogiAnalyzer-update-XXXXXX") || return 1
        if ! "$here/ShogiAnalyzer" --prepare-update "$job"; then
            rmdir "$job" 2>/dev/null
            return 1
        fi
        "$job/ShogiAnalyzer" --update-job "$job/job.json"
        result=$?
        "$here/ShogiAnalyzer" --cleanup-update "$job"
        return "$result"
    fi
    if [ -x "$here/.venv/bin/python" ]; then
        "$here/.venv/bin/python" "$here/installer/update.py"
    else
        python3 "$here/installer/update.py"
    fi
}
main "$@"; exit "$?"

#!/bin/sh
# Tests for the format_elapsed function in container/notify.
# Run: sh tests/test_notify.sh

FAILURES=0
TESTS=0

assert_eq() {
    TESTS=$((TESTS + 1))
    expected="$1"
    actual="$2"
    label="$3"
    if [ "$expected" != "$actual" ]; then
        echo "FAIL: $label — expected '$expected', got '$actual'"
        FAILURES=$((FAILURES + 1))
    fi
}

# Source the function (extract it so we can test it)
# We'll test by calling the notify script with a special --test-format flag
NOTIFY="$(dirname "$0")/../container/notify"

# Test format_elapsed directly via subshell sourcing
test_format() {
    # Source the script in a subshell to get the function, then call it
    result=$(sh -c ". '$NOTIFY' --source-only; format_elapsed $1")
    assert_eq "$2" "$result" "format_elapsed $1"
}

test_format 0 "0s"
test_format 1 "1s"
test_format 30 "30s"
test_format 59 "59s"
test_format 60 "1m 0s"
test_format 61 "1m 1s"
test_format 90 "1m 30s"
test_format 120 "2m 0s"
test_format 415 "6m 55s"
test_format 3599 "59m 59s"
test_format 3600 "1h 0m"
test_format 3661 "1h 1m"
test_format 7200 "2h 0m"
test_format 7322 "2h 2m"
test_format 86400 "24h 0m"

echo ""
echo "$TESTS tests, $FAILURES failures"
[ "$FAILURES" -eq 0 ]

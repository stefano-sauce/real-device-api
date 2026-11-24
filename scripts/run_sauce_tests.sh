#!/usr/bin/env bash
# Runs every test in this repo on Sauce Labs real devices (EU DC) through the Real Device Access API:
#   1. Python suite (tests/python): public + private devices, App Storage + App Store apps, web apps,
#      Sauce Connect tunnel, network capture.
#   2. Java sample (samples/java/demo): suite-per-session on one device, one recorded job per test.
# Every test is a recorded job in Real Device Access API > Test Results (video, screenshots, device log,
# Appium log, HAR), tagged repo:real-device-api plus platform/device/app/feature tags.
# Used by hand and by the daily cron job.
#
# Credentials: SAUCE_USERNAME / SAUCE_ACCESS_KEY from the environment, else read from the
# `export NAME=value` lines in ~/.zshrc (cron does not load the shell profile).
# Extra tags: SAUCE_TAGS (comma separated, e.g. "ci:cron") is appended to every job's tags.
#
# Usage: scripts/run_sauce_tests.sh            # everything
#        scripts/run_sauce_tests.sh python     # only the Python suite (or: java)
set -uo pipefail

REPO_DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
cd "$REPO_DIR" || exit 1

export PATH="/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

zshrc_var() { sed -n "s/^export $1=//p" "$HOME/.zshrc" 2>/dev/null | tail -1 | tr -d "\"'"; }
for var in SAUCE_USERNAME SAUCE_ACCESS_KEY; do
  [ -z "${!var:-}" ] && export "$var=$(zshrc_var "$var")"
  [ -z "${!var:-}" ] && { echo "ERROR: $var is not set (export it in ~/.zshrc)."; exit 1; }
done
export SAUCE_REGION="${SAUCE_REGION:-eu-central-1}"
export SAUCE_BUILD="${SAUCE_BUILD:-real-device-api $(date '+%F %H:%M')}"
export SAUCE_TAGS="${SAUCE_TAGS:-}"
export JAVA_HOME="${JAVA_HOME:-$(/usr/libexec/java_home 2>/dev/null)}"

# The access key must never reach a log.
mask() { "$@" 2>&1 | sed -u "s/$SAUCE_ACCESS_KEY/***/g"; return "${PIPESTATUS[0]}"; }

FAILED=0
step() {
  echo "=== $1 ==="
  shift
  if mask "$@"; then echo "SUCCESS: $*"; else echo "FAILURE: $*"; FAILED=1; fi
}
ARGS="$*"

if [ -z "$ARGS" ] || [[ " $ARGS " == *" python "* ]]; then
  if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
  .venv/bin/pip install -q --disable-pip-version-check -r tests/python/requirements.txt
  # Sauce Connect 5 (`sc`) must be installed for the tunnel tests: brew install saucelabs/sauce-connect/sauce-connect
  step "Python suite (pytest)" bash -c "cd tests/python && ../../.venv/bin/python -m pytest"
fi

if [ -z "$ARGS" ] || [[ " $ARGS " == *" java "* ]]; then
  step "Java sample (JUnit 5, suite-per-session)" mvn -q -f samples/java/demo/pom.xml clean test
fi

echo "Build: $SAUCE_BUILD"
exit $FAILED

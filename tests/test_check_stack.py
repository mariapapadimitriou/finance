"""ios/tools/check_stack.py fails closed (2026-11-16).

Run bare, it used to check only Transaction's size and print OK, so
TransactionDetailView.body.getter grew back over 32 KB on main unseen. These
only exercise its arguments, which it checks before touching Xcode.
"""

import os
import subprocess
import sys

TOOL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ios", "tools", "check_stack.py")


def run(*args):
    return subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True)


def test_bare_run_fails_and_says_what_to_pass():
    r = run()
    assert r.returncode == 2
    assert "--build" in r.stderr and "--dylib" in r.stderr
    assert "OK" not in r.stdout


def test_derived_with_no_build_in_it_fails(tmp_path):
    r = run("--derived", str(tmp_path))
    assert r.returncode == 2
    assert "Pearl.debug.dylib" in r.stderr


def test_missing_dylib_fails(tmp_path):
    r = run("--dylib", str(tmp_path / "Pearl.debug.dylib"))
    assert r.returncode == 2


def test_sizes_only_cannot_be_mixed_with_a_frame_check(tmp_path):
    r = run("--sizes-only", "--derived", str(tmp_path))
    assert r.returncode == 2

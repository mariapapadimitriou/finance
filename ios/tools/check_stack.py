#!/usr/bin/env python3
"""Check the iPhone app's stack use without running it (2026-11-14).

A Debug build crashed on the product owner's iPhone with "Thread stack size
exceeded" while TransactionDetailView's body ran. Two things made it big,
and this checks both, statically, with no simulator:

1. Stack frames. Every function's frame in the Debug build's
   Pearl.debug.dylib, read from its prologue (`sub sp, sp, #N`). Fails if
   any is over --limit (32 KB by default) and lists the biggest.
2. Transaction's size. It's copied into a fresh stack slot for every `t.`
   in a Debug SwiftUI body, and into every view that holds one. Compiles
   API/Models.swift for this Mac with a stand-in for ReviewAnswer, prints
   MemoryLayout sizes, and fails over --max-transaction (1,024 bytes).

    python3 ios/tools/check_stack.py --build /tmp/dd   # builds Debug for device first
    python3 ios/tools/check_stack.py --dylib path/to/Pearl.debug.dylib
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
IOS = os.path.dirname(HERE)


def frames(binary: str) -> dict[str, int]:
    p = subprocess.Popen(["xcrun", "llvm-objdump", "-d", "--no-show-raw-insn", binary],
                         stdout=subprocess.PIPE, text=True, bufsize=1 << 20)
    head = re.compile(r"^[0-9a-f]+ <(.+)>:$")
    sub = re.compile(r"\tsub\tsp, sp, #(0x[0-9a-f]+)(?:, lsl #(\d+))?")
    out: dict[str, int] = {}
    func = None
    for line in p.stdout:
        m = head.match(line)
        if m:
            func = m.group(1)
            continue
        m = sub.search(line)
        if m and func:
            out[func] = max(out.get(func, 0), int(m.group(1), 16) << int(m.group(2) or 0))
    p.wait()
    return out


def demangle(names: list[str]) -> list[str]:
    r = subprocess.run(["xcrun", "swift-demangle", "--simplified"], input="\n".join(names),
                       capture_output=True, text=True)
    return r.stdout.splitlines()


def sizes() -> dict[str, int]:
    pearl = os.path.join(IOS, "Pearl")
    with tempfile.TemporaryDirectory() as tmp:
        review = open(os.path.join(pearl, "Views/Review/ReviewView.swift")).read()
        enum = re.search(r"^enum ReviewAnswer \{(.*?)^\}", review, re.S | re.M).group(1)
        cases = [l for l in enum.splitlines() if re.match(r"^    case [a-z]", l)]
        open(os.path.join(tmp, "Stub.swift"), "w").write("enum ReviewAnswer {\n" + "\n".join(cases) + "\n}\n")
        types = ["Transaction", "Transaction.Splitting", "Transaction.Brief", "Transaction.Linked"]
        open(os.path.join(tmp, "main.swift"), "w").write(
            "".join(f'print("{t}", MemoryLayout<{t}>.size)\n' for t in types))
        exe = os.path.join(tmp, "sizes")
        arch = "arm64" if os.uname().machine == "arm64" else "x86_64"
        subprocess.run(["xcrun", "swiftc", "-target", f"{arch}-apple-macos14", "-o", exe,
                        os.path.join(pearl, "API/Models.swift"), os.path.join(pearl, "API/Boxed.swift"),
                        os.path.join(pearl, "App/Format.swift"), os.path.join(tmp, "Stub.swift"),
                        os.path.join(tmp, "main.swift")], check=True)
        out = subprocess.run([exe], capture_output=True, text=True, check=True).stdout
    return {k: int(v) for k, v in (l.rsplit(" ", 1) for l in out.splitlines())}


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--build", help="derivedData folder: build Debug for device into it first")
    a.add_argument("--dylib", help="an already built Pearl.debug.dylib")
    a.add_argument("--limit", type=int, default=32 * 1024)
    a.add_argument("--max-transaction", type=int, default=1024)
    a.add_argument("--top", type=int, default=15)
    args = a.parse_args()
    failed = False
    s = sizes()
    for k, v in s.items():
        print(f"MemoryLayout<{k}>.size = {v}")
    if s["Transaction"] > args.max_transaction:
        print(f"FAIL: Transaction is {s['Transaction']} bytes (limit {args.max_transaction})")
        failed = True
    dylib = args.dylib
    if args.build:
        r = subprocess.run(["xcodebuild", "build", "-project", "Pearl.xcodeproj", "-scheme", "Pearl",
                            "-configuration", "Debug", "-sdk", "iphoneos", "-destination", "generic/platform=iOS",
                            "-derivedDataPath", args.build, "CODE_SIGNING_ALLOWED=NO"],
                           cwd=IOS, capture_output=True, text=True)
        if r.returncode:
            print("\n".join(l for l in r.stdout.splitlines() if "error:" in l) or r.stdout[-2000:])
            return 1
        dylib = os.path.join(args.build, "Build/Products/Debug-iphoneos/Pearl.app/Pearl.debug.dylib")
    if dylib:
        f = frames(dylib)
        top = sorted(f.items(), key=lambda kv: -kv[1])[:args.top]
        for (name, v), pretty in zip(top, demangle([n for n, _ in top])):
            print(f"{v:>8,}  {pretty[:140]}")
        over = [(n, v) for n, v in f.items() if v > args.limit]
        if over:
            print(f"FAIL: {len(over)} frame(s) over {args.limit:,} bytes")
            failed = True
    print("FAIL" if failed else "OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

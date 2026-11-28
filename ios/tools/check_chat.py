#!/usr/bin/env python3
"""Check Pearl chat without a simulator (2026-11-15; Ask Pearl, THL-308).

1. Compiles ios/Pearl/Chat/ChatCore.swift for this Mac with API/Models.swift,
   Boxed.swift, Format.swift and a stand-in for ReviewAnswer (as
   check_stack.py does), plus ios/tools/chat_checks.swift, and runs the chat
   on a scripted model and a fake server: the screens it reaches, the words
   it says, and every write it makes.
2. Holds "nothing changes until she confirms" in the source:
   * only ChatCards.swift's buttons make a UserTap;
   * the model (CloudBrain, which asks Claude through Pearl's server) never
     names a writer, the executor, the engine or an APIClient, and never
     posts or puts;
   * in ChatCore.swift only ChatExecutor touches the writer;
   * Apple Intelligence is never used (THL-308): no FoundationModels, no
     PearlBrainLive.swift, nothing that checks for or mentions it.

    python3 ios/tools/check_chat.py

What only a real server with a key can show: Claude's own words, its tool
calls and speed. The server's side is in tests/test_ask_pearl.py, on a fake
client; the first production call is the product owner's smoke check.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
IOS = os.path.dirname(HERE)
PEARL = os.path.join(IOS, "Pearl")
CHAT = os.path.join(PEARL, "Chat")


def static_checks() -> list[str]:
    problems = []
    for root, _, files in os.walk(PEARL):
        for f in files:
            if not f.endswith(".swift"):
                continue
            path = os.path.join(root, f)
            src = open(path).read()
            if f not in ("ChatCards.swift", "ChatCore.swift") and re.search(r"\bUserTap\(", src):
                problems.append(f"{os.path.relpath(path, IOS)} makes a UserTap: only ChatCards.swift's buttons may")
    core = open(os.path.join(CHAT, "ChatCore.swift")).read()
    brain = re.search(r"^struct CloudBrain: PearlBrain \{(.*?)^\}", core, re.S | re.M)
    if not brain:
        problems.append("ChatCore.swift has no CloudBrain")
    else:
        for word in ("APIClient", "ChatWriting", "ChatExecutor", "ChatEngine", "APIChatWriting", "UserTap",
                     ".post(", ".put(", ".patch(", ".delete("):
            if word in brain.group(1):
                problems.append(f"CloudBrain names {word}: the model may only read")
    if os.path.exists(os.path.join(CHAT, "PearlBrainLive.swift")):
        problems.append("PearlBrainLive.swift is back: Apple Intelligence is never used (THL-308)")
    for root, _, files in os.walk(PEARL):
        for f in files:
            if f.endswith(".swift"):
                src = open(os.path.join(root, f)).read()
                for word in ("FoundationModels", "SystemLanguageModel", "Apple Intelligence",
                             "PearlIntelligence", "LanguageModelSession"):
                    if word in src:
                        problems.append(f"{f} mentions {word}: Apple Intelligence is never used (THL-308)")
    executor = re.search(r"^struct ChatExecutor \{(.*?)^\}", core, re.S | re.M)
    rest = core.replace(executor.group(0), "") if executor else core
    if re.search(r"\bwriter\.[a-z]", rest):
        problems.append("ChatCore.swift uses the writer outside ChatExecutor")
    tools = re.search(r"^actor ChatTools \{(.*?)^\}", core, re.S | re.M)
    if not tools or re.search(r"Writ|Executor|Engine|APIClient", tools.group(1)):
        problems.append("ChatTools holds something that can write")
    return problems


def run_checks() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        review = open(os.path.join(PEARL, "Views/Review/ReviewView.swift")).read()
        enum = re.search(r"^enum ReviewAnswer \{(.*?)^\}", review, re.S | re.M).group(1)
        cases = [line for line in enum.splitlines() if re.match(r"^    case [a-z]", line)]
        open(os.path.join(tmp, "Stub.swift"), "w").write("enum ReviewAnswer {\n" + "\n".join(cases) + "\n}\n")
        exe = os.path.join(tmp, "chat_checks")
        arch = "arm64" if os.uname().machine == "arm64" else "x86_64"
        build = subprocess.run(
            ["xcrun", "swiftc", "-parse-as-library", "-target", f"{arch}-apple-macos14", "-o", exe,
             os.path.join(PEARL, "API/Models.swift"), os.path.join(PEARL, "API/Boxed.swift"),
                        os.path.join(PEARL, "API/Changed.swift"),
             os.path.join(PEARL, "App/Format.swift"), os.path.join(tmp, "Stub.swift"),
             os.path.join(CHAT, "ChatCore.swift"), os.path.join(HERE, "chat_checks.swift")],
            capture_output=True, text=True)
        if build.returncode:
            print(build.stderr[-4000:])
            return 1
        r = subprocess.run([exe], capture_output=True, text=True)
        print(r.stdout.strip())
        if r.stderr.strip():
            print(r.stderr.strip()[-2000:])
        return r.returncode


def main() -> int:
    problems = static_checks()
    for p in problems:
        print("FAIL:", p)
    code = run_checks()
    ok = not problems and code == 0
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

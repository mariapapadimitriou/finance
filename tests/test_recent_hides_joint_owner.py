"""Who was it with? on a joint purchase never lists the joint account's other
owner, whose part is already off, and refuses them typed (2026-11-25)."""

from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "ios/Pearl/Views/Transactions/SplitFlow.swift").read_text()


def between(a, b):
    i = SRC.index(a)
    return SRC[i:SRC.index(b, i)]


def test_never_listed_under_recent():
    choices = between("private var choices: [String]", "private func holder")
    assert "where !out.contains(n) && holder(n) == nil" in choices


def test_by_the_same_rule_as_the_server():
    holder = between("private func holder(_ name: String)", "private var refusal")
    assert "t.joint.isEmpty ? nil : t.jointPeople.first { samePerson($0, name) }" in holder


def test_not_from_contacts_and_not_typed():
    who = between("private var who: some View", "private func personRow")
    assert ".filter { holder($0) == nil }" in who
    assert "if let refusal = refusal { APErrorLine(text: refusal) }" in who
    assert "if !q.isEmpty, refusal == nil," in who
    assert "part is already off." in between("private var refusal", "private func addTyped")
    assert "refusal == nil else { return }" in between("private func addTyped()", "private func remove")
    assert ": step == 0 ? refusal != nil ||" in between("private var footer: some View", "private func save()")
    # P11 (fewer taps): Add someone new refuses a joint holder the same way.
    flow = open("ios/Pearl/Views/Transactions/SplitFlow.swift").read()
    assert 'refuse: { n in holder(n).map { "\\(possessive($0)) part is already off." } }' in flow
    assert "&& holder(n) == nil" in flow[flow.index("private var chipNames"):]

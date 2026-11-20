"""The people picker finds every contact (product owner, 2026-11-19:
"I can't find all my contacts when I look for shared accounts")."""
import re
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1]
       / "ios/Pearl/Views/Transactions/JointSplitViews.swift").read_text()


def test_every_contact_is_loaded():
    # No stop after N contacts.
    assert "stop.pointee = true" not in SRC
    assert not re.search(r"out\.count\s*>=", SRC)


def test_search_looks_through_everyone_before_any_cap():
    body = SRC[SRC.index("private func contactMatches"):]
    body = body[:body.index("\n    }\n")]
    assert "matches(c)" in body
    # The cap applies only while browsing (no search typed).
    assert "q.isEmpty ? Array(all.prefix(Self.browseCap)) : all" in body
    # No other contact list caps before filtering.
    assert ".prefix(60)" not in SRC


def test_nameless_contacts_fall_back_to_nickname_then_company():
    assert "CNContactNicknameKey" in SRC and "CNContactOrganizationNameKey" in SRC
    assert SRC.index("c.nickname") < SRC.index("c.organizationName")


def test_limited_access_can_share_more():
    assert "ContactAccessButton(queryString: q)" in SRC
    assert "status == .limited" in SRC
    # Both pickers (split and joint) show the hint and the button.
    assert SRC.count("moreContactsLine") >= 3

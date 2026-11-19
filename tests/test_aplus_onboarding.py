"""A+ onboarding and sign-in (REDESIGN-13, boards G6-*, G5-Setup, G5-Lock):
the approved new function, read from the Swift source."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ONB = ROOT / "ios/Pearl/Views/Onboarding"


def src(name):
    return (ONB / name).read_text(encoding="utf-8")


def test_one_progress_strip():
    kit = src("OnboardingKit.swift")
    assert "struct SetupStrip" in kit and '"Part \\(part) of 3 \\u{00B7} \\(name)"' in kit
    for f in ONB.glob("*.swift"):
        assert "ShellProgress(" not in f.read_text(encoding="utf-8"), f.name
    assert 'part: 2, partName: "Link your bank"' in src("SetupFlow.swift")
    assert 'partName: "Your money"' in src("PayAndBillsView.swift")
    assert 'part: 3, partName: "Your money"' in src("SavingShareView.swift")


def test_welcome_line():
    auth = src("AuthFlow.swift")
    assert "See what\\u{2019}s yours to spend, and plan ahead." in auth
    assert "Assess, plan ahead" not in auth


def test_not_you_on_face_id_return():
    auth = src("AuthFlow.swift")
    assert '"Not you? Use a different email"' in auth
    i = auth.index('"Not you? Use a different email"')
    assert 'email = ""' in auth[i:i + 400], "goes to the plain sign-in with the email cleared"


def test_plaid_line_in_the_app():
    flow = src("SetupFlow.swift")
    assert '"In Profile \\u{203A} Accounts"' in flow
    assert "my.plaid.com" not in flow


def test_found_pay_answers_on_the_row():
    pb = src("PayAndBillsView.swift")
    assert "struct FoundPayRow" in pb
    assert 'APPillButton(title: "Yes"' in pb and 'APPillButton(title: "No", quiet: true' in pb
    assert '"api/income-bills/pay/answer"' in pb
    assert 'await answer(c.payer, "yes")' in pb and 'await answer(c.payer, "no")' in pb


def test_safety_net_hidden_while_save_is_parked():
    allow = src("AllowanceView.swift")
    assert "Build your safety net" not in allow.split("struct SafetyNetTip")[0]
    assert "SafetyNetTip()" not in allow


def test_password_rules_tick_green_and_only_failing_red():
    kit = src("OnboardingKit.swift")
    i = kit.index("struct PasswordChecks")
    checks = kit[i:kit.index("struct CodeWells")]
    assert "s == .met ? Pearl.moneyIn : s == .failed ? Pearl.danger : Pearl.muted" in checks
    assert '"At least 12 characters \\u{00B7} \\(rules.more) more"' in checks


def test_no_stock_dialogs_on_the_boards_screens():
    for name in ("AuthFlow.swift", "SetupFlow.swift", "FaceIDViews.swift", "AllowanceView.swift",
                 "SavingShareView.swift", "AccountSetupViews.swift", "OnboardingKit.swift"):
        text = src(name)
        for stock in (".alert(", ".confirmationDialog(", ".actionSheet("):
            assert stock not in text, (name, stock)
    # A-10 Can't get the code? is a Pearl sheet over the code page.
    assert "CantGetCodeSheet(" in src("AuthFlow.swift")


def test_lock_screen_words():
    face = src("FaceIDViews.swift")
    assert '"Pearl is locked"' in face and '"Sign in with password"' in face
    assert '"Turn it on in iPhone Settings › Face ID & Passcode."' in face

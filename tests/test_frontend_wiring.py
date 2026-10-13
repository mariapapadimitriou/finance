"""Invariants between the shell, the groups, and the panels they render.

These read the source rather than run it. There is no JavaScript test runner
here, and the alternative to a static check was no check at all — for a class
of bug that is invisible in review and looks, in the browser, like a button that
does nothing.

The navigation has two levels now: four groups in the sidebar, each holding one
or more panels behind a section switcher. Panels still link to each other by
panel key, which only works because `resolve` maps a panel key back to the group
that owns it — so the checks below are mostly about that mapping staying whole.

Each test fails loudly if it cannot find what it expects to parse, so a
restructured file reports that it needs updating rather than passing silently.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
APP = SRC / "App.jsx"
# The map of panels, groups and aliases. It lives apart from the shell so that
# components naming a destination in a sentence can ask what it is called.
NAV = SRC / "nav.js"


@pytest.fixture(scope="module")
def source() -> str:
    text = APP.read_text(encoding="utf-8")
    assert text.strip(), "src/App.jsx is empty"
    return text


@pytest.fixture(scope="module")
def nav() -> str:
    text = NAV.read_text(encoding="utf-8")
    assert text.strip(), "src/nav.js is empty"
    return text


@pytest.fixture(scope="module")
def panels(nav) -> set[str]:
    """The keys of the PANELS map."""
    m = re.search(r"const PANELS = \{(.*?)\n\};", nav, re.S)
    assert m, "could not find `const PANELS = {...}` in nav.js — update this test"
    keys = set(re.findall(r"^\s{2}(\w+):\s*\{", m.group(1), re.M))
    assert len(keys) > 5, f"only parsed {keys} out of PANELS — update this test"
    return keys


@pytest.fixture(scope="module")
def groups(nav) -> dict[str, list[str]]:
    """Group key -> the panel keys it holds, in order."""
    m = re.search(r"const GROUPS = \[(.*?)\n\];", nav, re.S)
    assert m, "could not find `const GROUPS = [...]` in nav.js — update this test"
    # `short:` is the optional phone-width label, and may push `panels` onto
    # the next line.
    found = re.findall(r"key: '([^']+)', label: '[^']*',"
                       r"(?:\s*short: '[^']*',)?\s*panels: \[([^\]]+)\]",
                       m.group(1))
    assert found, "could not parse any group out of GROUPS — update this test"
    return {key: re.findall(r"'([^']+)'", panels) for key, panels in found}


@pytest.fixture(scope="module")
def aliases(nav) -> dict[str, str]:
    """Old panel keys that now point at the panel which absorbed them."""
    m = re.search(r"const ALIASES = \{(.*?)\};", nav, re.S)
    assert m, "could not find `const ALIASES = {...}` in nav.js — update this test"
    return dict(re.findall(r"(\w+):\s*'([^']+)'", m.group(1)))


@pytest.fixture(scope="module")
def rendered(source) -> set[str]:
    """Panel keys that actually have a branch rendering them."""
    keys = set(re.findall(r"panel === '([^']+)'", source))
    assert keys, "no `panel === '...'` branches found — update this test"
    return keys


def _string_list(source: str, name: str) -> list[str]:
    m = re.search(rf"const {name} = \[(.*?)\];", source, re.S)
    assert m, f"could not find `const {name} = [...]` in App.jsx — update this test"
    return re.findall(r"'([^']+)'", m.group(1))


class TestEveryPanelIsReachableAndRendered:
    def test_every_panel_belongs_to_exactly_one_group(self, panels, groups):
        """A panel in no group cannot be reached; one in two is ambiguous —
        `resolve` would send you to whichever appeared first."""
        owners: dict[str, list[str]] = {key: [] for key in panels}
        for group, members in groups.items():
            for key in members:
                assert key in panels, (
                    f"group '{group}' lists panel '{key}', which is not in PANELS")
                owners[key].append(group)

        orphans = sorted(k for k, g in owners.items() if not g)
        assert not orphans, f"panels in no group, so unreachable: {orphans}"
        shared = sorted(k for k, g in owners.items() if len(g) > 1)
        assert not shared, f"panels claimed by more than one group: {shared}"

    def test_every_panel_is_rendered(self, panels, rendered):
        missing = sorted(panels - rendered)
        assert not missing, (
            f"{missing} appear in PANELS and the section switcher, but nothing "
            "renders them — the section would open onto an empty page")

    def test_nothing_is_rendered_that_is_not_a_panel(self, panels, rendered):
        stray = sorted(rendered - panels)
        assert not stray, (
            f"{stray} have a render branch but are in no group, so no "
            "navigation can reach them")

    def test_the_import_panel_is_reachable_again(self, groups):
        """It used to be hidden from the strip entirely, which left the import
        history unreachable in normal use once Plaid was working."""
        owners = [g for g, members in groups.items() if "import" in members]
        assert owners, "'import' is in no group, so nothing can reach it"


class TestLinksBetweenPanels:
    def test_every_alias_points_somewhere_real(self, panels, groups, aliases):
        """An alias is how a panel that was folded into another one keeps its
        old links working. One pointing at nothing is worse than no alias at
        all: `resolve` falls through to Allowance, so the button appears to work."""
        assert aliases, "ALIASES is empty — remove the fixture if it is gone"
        for key, target in aliases.items():
            assert key not in panels, (
                f"'{key}' is aliased but is also a panel — the alias wins in "
                "`resolve`, so the panel is unreachable")
            assert target in panels or target in groups, (
                f"alias '{key}' points at '{target}', which is neither")

    def test_every_link_target_resolves(self, panels, groups, aliases):
        """Panels navigate by panel key — `onTab('piggy')` — and a key that is
        neither a panel, a group nor an alias silently lands you on Allowance."""
        targets: dict[str, list[str]] = {}
        for path in sorted(SRC.rglob("*.jsx")):
            text = path.read_text(encoding="utf-8")
            for key in re.findall(r"onTab\('([^']+)'\)", text):
                targets.setdefault(key, []).append(path.name)
            for key in re.findall(r"\bgo\('([^']+)'\)", text):
                targets.setdefault(key, []).append(path.name)

        assert targets, "no onTab('...') calls found anywhere — update this test"
        valid = panels | set(groups) | set(aliases)
        bad = {k: v for k, v in targets.items() if k not in valid}
        assert not bad, f"link targets that resolve to nothing: {bad}"


class TestTheEmptyLedger:
    def test_the_empty_state_only_offers_panels_it_will_render(self, source):
        """The bug this exists to prevent.

        When the ledger is empty most panels are hidden behind an empty state. A
        button there that points at a hidden panel sets the destination, the
        empty state renders over it again, and nothing appears to happen — which
        is exactly how it was reported.
        """
        allowed = _string_list(source, "WORKS_WHEN_EMPTY")
        assert allowed, "WORKS_WHEN_EMPTY is empty"

        guard = re.search(r"if \(summary\.empty && (.+?)\) \{", source)
        assert guard, "could not find the empty-ledger guard — update this test"
        assert "WORKS_WHEN_EMPTY" in guard.group(1), (
            "the empty-ledger guard no longer consults WORKS_WHEN_EMPTY")
        # It has to test the panel, not the group: a group whose first panel
        # works when empty would otherwise let through every panel beside it.
        assert "includes(panel)" in guard.group(1), (
            "the guard checks something other than the active panel")

        block = re.search(r"<Empty title=.*?</Empty>", source, re.S)
        assert block, "could not find the <Empty> block — update this test"

        targets = set(re.findall(r"go\('([^']+)'\)", block.group(0)))
        assert targets, "the empty state offers no way out of itself"

        unreachable = sorted(t for t in targets if t not in allowed)
        assert not unreachable, (
            f"the empty state links to {unreachable}, which it will not render; "
            f"add them to WORKS_WHEN_EMPTY or point the button elsewhere")

    def test_the_guarded_panels_are_real(self, panels, source):
        for key in _string_list(source, "WORKS_WHEN_EMPTY"):
            assert key in panels, (
                f"WORKS_WHEN_EMPTY names '{key}', which is not a panel")


class TestTheMonthSelector:
    def test_it_is_offered_on_the_panels_that_read_a_month(self, panels, source):
        """It is shown per panel, not per group: Insights needs it and its
        neighbours do not. Budgets (THL-168) is always this month."""
        m = re.search(r"showMonth=\{(.+?)\}", source)
        assert m, "could not find the showMonth prop — update this test"
        assert "includes(panel)" in m.group(1), (
            "showMonth no longer keys off the active panel")
        for key in re.findall(r"'([^']+)'", m.group(1)):
            assert key in panels, f"showMonth names '{key}', which is not a panel"


class TestNumberInputsAcceptTheAmountsPeopleType:
    """The `step` attribute is a validity rule, not a convenience.

    `min="1" step="50"` on the piggy bank target meant the browser considered
    1300, 2400 and every other round figure invalid — the two nearest valid
    values being 1251 and 1301. Chrome then refuses to submit the form and
    reports it on a tooltip nobody sees, so the button does nothing. This is
    exactly the class of bug this file exists for: invisible in review, and
    indistinguishable in use from a dead button.

    Cents are the only step a money field may impose. A count — years and
    months — may ask for whole numbers, and says so with inputMode="numeric".
    """

    def test_no_money_field_rejects_an_ordinary_amount(self):
        inputs = re.compile(r'<input\b[^>]*?type="number"[^>]*?>', re.S)
        offenders = []
        for path in sorted(SRC.rglob("*.jsx")):
            for tag in inputs.findall(path.read_text(encoding="utf-8")):
                m = re.search(r'step="([^"]+)"', tag)
                if not m or m.group(1) in ("any", "0.01"):
                    continue
                if m.group(1) == "1" and 'inputMode="numeric"' in tag:
                    continue
                offenders.append(f"{path.name}: step=\"{m.group(1)}\"")
        assert not offenders, (
            "number inputs whose step makes ordinary amounts invalid, so the "
            f"form silently refuses to submit: {offenders}")


class TestTheMortgagePageIsGone:
    def test_no_panel_route_or_calls(self):
        """Mortgage payments are read from the accounts now; the calculator
        that declared them by hand went, and an old link lands on Plan."""
        assert not (SRC / "panels" / "MortgagePanel.jsx").exists()
        nav = (SRC / "nav.js").read_text(encoding="utf-8")
        assert "mortgage: 'plan'" in nav
        assert "'mortgage'" not in nav.split("export const GROUPS")[1].split("];")[0]
        for name in ("App.jsx", "api.js"):
            assert "ortgage" not in (SRC / name).read_text(encoding="utf-8"), name


def _visible_text(source: str) -> str:
    """JSX with its comments removed — what could reach the screen."""
    source = re.sub(r"\{/\*.*?\*/\}", "", source, flags=re.S)   # {/* … */}
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)       # /* … */
    return re.sub(r"(?m)^\s*//.*$|(?<=[;{}(),])\s*//.*$", "", source)


class TestNoSentenceNamesATabThatIsGone:
    """The freshness notice told people to "sync on the Banks tab" for months
    after Banks became Connections, inside a group now called Settings.
    Destinations are named by `<GoTo>` from nav.js now; this catches anything
    that goes back to writing one by hand."""

    def test_every_tab_named_in_a_sentence_exists(self, nav):
        labels = set(re.findall(r"label: '([^']+)'", nav))
        assert labels, "no labels parsed from nav.js — update this test"

        stale = []
        for path in sorted(SRC.rglob("*.jsx")):
            text = _visible_text(path.read_text(encoding="utf-8"))
            for name in re.findall(r"\bthe ([A-Z][\w&]*(?: [\w&]+)*?) tab\b", text):
                if name not in labels:
                    stale.append(f"{path.name}: 'the {name} tab'")
        assert not stale, (
            "sentences naming tabs that do not exist — use <GoTo to=…> so the "
            f"name comes from nav.js: {stale}")

    def test_the_comment_stripper_is_not_hiding_everything(self):
        sample = "<p>Go to the Banks tab</p>{/* the Old tab */}\n// the Gone tab"
        visible = _visible_text(sample)
        assert "the Banks tab" in visible
        assert "Old" not in visible and "Gone" not in visible


class TestExplanationsRememberThemselves:
    def test_no_explanations_have_crept_back(self):
        """The screens say figures and states, not reasons. A "Why?"
        expander, an assumption paragraph or a card subtitle is the scaffolding
        that was removed so the pages read at a glance."""
        offenders = []
        for path in sorted(SRC.rglob("*.jsx")):
            # Pearl's sign-in and onboarding follow the Figma handoff, where a
            # field's one-line hint ("We'll send a code to check it's you") is
            # part of the input component.
            if "pearl" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for pattern in (r"<Why\b", r'className="assumption"', r"\bhint="):
                if re.search(pattern, text):
                    offenders.append(f"{path.name}: {pattern}")
        assert not offenders, f"explanation scaffolding is back: {offenders}"


class TestPicturesNotArithmetic:
    def test_the_first_tab_is_home(self, nav):
        """Home replaces the old landing tab (THL-44, THL-125): it is the page
        people open the app for, and it lands there."""
        first = re.search(r"GROUPS = \[\s*(?://[^\n]*\n\s*)*\{ key: '(\w+)', label: '([^']+)'", nav)
        assert first, "could not find the first group in nav.js"
        assert first.groups() == ("home", "Home")
        assert "label: 'Today'" not in nav

    def test_this_month_keeps_its_ninety_day_chart(self):
        """It was dropped once in a redesign; it is wanted."""
        text = (SRC / "panels" / "OverviewPanel.jsx").read_text(encoding="utf-8")
        assert "dailySpendConfig(" in text

    def test_no_sums_of_terms_are_back(self):
        """The + − × ÷ = rows were replaced by rings with their parts beside
        them. A sum drawn in boxes is the thing that was asked to go."""
        offenders = [p.name for p in sorted(SRC.rglob("*.jsx"))
                     if 'className="sum"' in p.read_text(encoding="utf-8")]
        assert not offenders, f"arithmetic rows are back in: {offenders}"


class TestLessToRead:
    def test_cut_back_and_retirement_are_gone(self, groups, aliases, panels):
        assert "savings" not in groups and "savings" not in panels
        assert "subscriptions" not in aliases
        assert "retirement" not in panels
        assert not any("retirement" in members for members in groups.values())
        for name in ("SavingsPanel.jsx", "RetirementPanel.jsx", "SubscriptionsPanel.jsx"):
            assert not (SRC / "panels" / name).exists()

    def test_the_piggy_banks_have_a_title_and_no_tiles(self):
        text = (SRC / "panels" / "PiggyPanel.jsx").read_text(encoding="utf-8")
        assert "<Tile" not in text
        assert ">\n        Piggy banks\n" in text
        assert "for spending on your cards" in text


class TestPlanSetup:
    def test_saving_defaults_to_a_fifth_of_take_home(self):
        """The goal is a share of take-home — 20% until you set one — so its
        dollars follow take-home; it is saved as that share, not as dollars."""
        text = (SRC / "panels" / "PlanPanel.jsx").read_text(encoding="utf-8")
        assert "DEFAULT_RATE = 20" in text
        assert "savePlanSetup(Number(income) || 0, (Number(rate) || 0) / 100)" in text


class TestHomeIsWhereTheAppLands:
    """Pearl THL-9 / THL-44 / THL-125: Home replaces the old landing tab, and
    the Allowance page's jobs move onto it (THL-166, THL-167)."""

    def test_the_app_opens_on_home(self):
        text = (SRC / "App.jsx").read_text(encoding="utf-8")
        assert ": isPathUrl() ? 'growth' : 'home'" in text   # anything else lands on Home
        assert "panel === 'home'" in text and "<HomePanel" in text

    def test_old_links_to_the_allowance_land_on_home(self, aliases):
        assert aliases.get("today") == "home"
        assert not (SRC / "panels" / "TodayPanel.jsx").exists()

    def test_home_reads_one_payload(self):
        text = (SRC / "panels" / "HomePanel.jsx").read_text(encoding="utf-8")
        assert "getHome()" in text and "How we worked this out" in text


class TestAccountsInTheApp:
    def test_plaid_syncs_when_the_app_opens(self):
        text = (SRC / "App.jsx").read_text(encoding="utf-8")
        assert "syncPlaid()" in text

    def test_sign_in_offers_passkeys_codes_and_sign_up(self):
        text = (SRC / "pearl" / "SignedOut.jsx").read_text(encoding="utf-8")
        assert "getPasskey(" in text and "startCode(" in text and "verifyCode(" in text
        assert "Create an account" in text
        # Accounts that still have a password can use it.
        assert 'autoComplete="username"' in text and "login(" in text

    def test_new_accounts_set_up_before_the_app_opens(self):
        text = (SRC / "App.jsx").read_text(encoding="utf-8")
        assert "<Onboarding" in text and "user.onboarding.done" in text


class TestTheSetupChecklistGoesSomewhereReal:
    def test_every_step_names_a_destination_that_exists(self, tmp_path, panels,
                                                        groups, aliases):
        """The checklist's buttons take their destination from the server, so
        the static link check above cannot see them."""
        from app import create_app
        app = create_app(str(tmp_path / "setup.db"))
        app.config.update(TESTING=True)
        with app.test_client() as c:
            steps = c.get("/api/setup").get_json()["steps"]
        valid = panels | set(groups) | set(aliases)
        bad = {s["id"]: s["tab"] for s in steps if s["tab"] not in valid}
        assert not bad, f"setup steps pointing nowhere: {bad}"


class TestTheSidebarIsThl104s:
    def test_home_transactions_goals_growth_and_profile(self, groups):
        assert list(groups) == ["home", "transactions", "goals", "growth", "profile"]

    def test_growth_opens_on_the_path(self, groups):
        """THL-129 GR-01: Path, then Insights, Projections and Budgets."""
        assert groups["growth"][:3] == ["path", "overview", "projections"]
        assert "overview" not in groups

    def test_the_path_page_has_an_address(self):
        text = (SRC / "App.jsx").read_text(encoding="utf-8")
        assert "isPathUrl()" in text and "writePathUrl()" in text


class TestOneReviewQueue:
    def test_the_badge_counts_the_review_queue(self):
        text = (SRC / "App.jsx").read_text(encoding="utf-8")
        assert "getReview()" in text and "counts={{ transactions: data.review }}" in text

    def test_review_holds_every_kind_and_the_unsorted_question(self):
        text = (SRC / "panels" / "NeedsALook.jsx").read_text(encoding="utf-8")
        for kind in ("unsorted", "money_in", "unsure_category", "income_type", "three_pay_month"):
            assert f"data.{kind}" in text, kind
        assert "<WhereDidThisGo" in text
        assert "Remember where ${kind} to ${it.to} go" in text
        app = (SRC / "App.jsx").read_text(encoding="utf-8")
        assert "<NeedsALook" in app and "ReviewPanel" not in app

    def test_rows_can_be_excluded_and_put_back(self):
        tx = (SRC / "panels" / "TransactionsPanel.jsx").read_text(encoding="utf-8")
        assert "excludeTransaction(" in tx and "includeTransaction(" in tx
        assert "__excluded__" in tx


class TestWhereDidThisGoIsPerTransfer:
    def test_rows_not_groups_and_no_rule(self):
        tx = (SRC / "panels" / "TransactionsPanel.jsx").read_text(encoding="utf-8")
        card = tx[tx.index("export function WhereDidThisGo"):]
        card = card[:card.index("\n}\n")]
        assert "data?.transfers" in card and "data?.groups" not in card
        assert "sortTransfers([r.id], category, false)" in card
        assert "Remember where these go" not in card


class TestPearlTransactionsList:
    """THL-122: the Pearl list replaces Every charge, and its rules hold."""

    def test_the_group_opens_on_the_list(self):
        nav = (SRC / "nav.js").read_text(encoding="utf-8")
        assert "panels: ['transactions', 'review', 'trips']" in nav
        app = (SRC / "App.jsx").read_text(encoding="utf-8")
        assert "<TransactionsList" in app and "<TransactionsPanel" not in app

    def test_kit_names_no_colour_of_its_own(self):
        css = (SRC / "pearl" / "kit.css").read_text(encoding="utf-8")
        assert not re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", css), \
            "colours come from tokens.css"

    def test_amounts_never_carry_a_minus(self):
        kit = (SRC / "pearl" / "kit.jsx").read_text(encoding="utf-8")
        body = kit[kit.index("export function txAmount"):]
        body = body[:body.index("\n}\n")]
        assert "Math.abs(" in body, "the amount is shown without its sign"
        assert "`+${text}`" in body, "money in is marked with a plus"

    def test_suggested_chip_is_told_apart_without_colour(self):
        kit = (SRC / "pearl" / "kit.jsx").read_text(encoding="utf-8")
        assert "suggested by Pearl" in kit and "name=\"help\"" in kit
        css = (SRC / "pearl" / "kit.css").read_text(encoding="utf-8")
        assert re.search(r"\.pk-cat\.suggested\s*\{[^}]*dashed", css)


class TestDesignTokens:
    """THL-106: the Design System export is the one source of the variables."""

    TOKENS = SRC / "tokens"

    def test_the_export_is_vendored_whole(self):
        for name in ("tokens.css", "tokens.json", "tokens.ts"):
            text = (self.TOKENS / name).read_text(encoding="utf-8")
            assert "Do not edit by hand" in text, name
        data = json.loads((self.TOKENS / "tokens.json").read_text(encoding="utf-8"))
        assert set(data["color"]) == {"light", "dark"}
        assert set(data["color"]["light"]) == set(data["color"]["dark"])

    def test_loaded_before_the_shell(self):
        main = (SRC / "main.jsx").read_text(encoding="utf-8")
        tokens = main.index("import './tokens/tokens.css'")
        assert tokens < main.index("import App from") < main.index("import './styles.css'")

    def test_the_kit_keeps_no_copy_of_the_palette(self):
        css = (SRC / "pearl" / "tokens.css").read_text(encoding="utf-8")
        assert not re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", css)
        assert not re.search(r"--(pearl|blush|rose|lagoon|ocean|mist|gold)-\d+\s*:", css)

    def test_the_kit_uses_the_v3_semantic_tokens(self):
        css = (SRC / "pearl" / "kit.css").read_text(encoding="utf-8")
        for token in ("--border-strong", "--border-focus", "--border-error",
                      "--surface-scrim", "--surface-disabled", "--ink-disabled"):
            assert f"var({token})" in css, token


class TestChangeCategory:
    """THL-123 R-02/R-03: Change category says what it will do, and can be undone."""

    def test_the_picker_previews_and_groups(self):
        src = (SRC / "panels" / "CategoryPicker.jsx").read_text(encoding="utf-8")
        assert "previewCategory(" in src, "the impact line comes from the server"
        for title in ("'Essentials'", "'Lifestyle'", "'Savings'", "'Income'", "'Not spending'"):
            assert title in src, title
        assert "Apply to all from ${tx.merchant}" in src

    def test_the_detail_panel_uses_it(self):
        src = (SRC / "panels" / "TransactionDetail.jsx").read_text(encoding="utf-8")
        assert "<CategoryPicker" in src and "function ChangeCategory" not in src
        assert "back={{" in src, "the step has a back link naming the transaction"

    def test_the_list_offers_undo(self):
        src = (SRC / "panels" / "TransactionsList.jsx").read_text(encoding="utf-8")
        assert "<ActionToast" in src and "undoChange(" in src
        assert "flash={flash.has(r.id)}" in src


class TestSplitsAndRepayments:
    """THL-124 S-01 to S-04: split with people; repayments suggested and linked."""

    def test_split_this_and_its_summary(self):
        src = (SRC / "panels" / "Splits.jsx").read_text(encoding="utf-8")
        for text in ("Only your share counts toward your spending.", "Add someone",
                     "Watch for ${names(people)} paying me back", "Save split",
                     "Paid back {shortDate(p.paid_on)}", "Owes ${txAmount(p.owes)}"):
            assert text in src, text
        assert "MAX_PEOPLE = 8" in src

    def test_repayment_suggestion_and_link(self):
        src = (SRC / "panels" / "Splits.jsx").read_text(encoding="utf-8")
        for text in ("Is {match.name} paying you back for this?", "Exact match",
                     "Which split is this for?", "None of these",
                     "Paid back part of it? Pick the split and we’ll keep the rest open."):
            assert text in src, text
        detail = (SRC / "panels" / "TransactionDetail.jsx").read_text(encoding="utf-8")
        assert "Yes, link them" in detail and "No, it’s something else" in detail
        assert "linkPayback(o.charge_id, tx.id, o.name)" in detail
        review = (SRC / "panels" / "NeedsALook.jsx").read_text(encoding="utf-8")
        assert "it.guess?.action === 'split'" in review

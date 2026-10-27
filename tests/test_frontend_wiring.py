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

    def test_linking_a_bank_is_still_reachable(self, groups, aliases):
        """Connections went in C1, and with it the page that linked, signed
        in to and synced a bank. Those moved to Accounts, and every old link
        to Connections has to land there rather than on Home."""
        owners = [g for g, members in groups.items() if "accounts" in members]
        assert owners, "'accounts' is in no group, so a bank cannot be linked"
        assert aliases.get("banks") == "accounts"
        accounts = (SRC / "panels" / "AccountsPanel.jsx").read_text(encoding="utf-8")
        for call in ("createLinkToken(", "exchangePublicToken(", "syncPlaid(",
                     "Reconnect"):
            assert call in accounts, f"Accounts no longer does {call}"

    def test_nothing_links_to_a_removed_page(self):
        """Trips, From a file, Categories and Connections (C1) are gone; an
        onTab to one would only work by way of an alias."""
        stale = []
        for path in sorted(SRC.rglob("*.jsx")):
            text = path.read_text(encoding="utf-8")
            for key in ("banks", "import", "categories"):
                if re.search(rf"""(onTab\??\.?\(|go\(|to=)['"]{key}['"]""", text):
                    stale.append(f"{path.name}: {key}")
        assert not stale, f"links to removed pages: {stale}"


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
    def test_the_shell_picks_no_month(self, source):
        """Growth › Insights (THL-196 GR-28) has its own month switcher, and
        it was the only page that read the shell's; Budgets (THL-168) is
        always this month. So the shell's picker went with the old page."""
        assert "showMonth" not in source and "month-select" not in source
        page = (SRC / "panels" / "InsightsPanel.jsx").read_text(encoding="utf-8")
        assert "<MonthSwitcher" in page


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
        that declared them by hand went, and an old link lands on Income and
        bills, where a mortgage payment is a regular bill."""
        assert not (SRC / "panels" / "MortgagePanel.jsx").exists()
        nav = (SRC / "nav.js").read_text(encoding="utf-8")
        assert "mortgage: 'income'" in nav
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



class TestIncomeAndBillsReplacedThePlan:
    """THL-45 / THL-127: the income and bills check replaced the prototype
    Income and commitments page and the piggy banks under it. Goals'
    treasure chests are the piggy banks now."""

    def test_the_old_pages_are_gone(self, panels, aliases):
        for name in ("PlanPanel.jsx", "PiggyPanel.jsx"):
            assert not (SRC / "panels" / name).exists(), name
        assert "plan" not in panels
        assert aliases["plan"] == "income" and aliases["piggy"] == "home"
        api = (SRC / "api.js").read_text(encoding="utf-8")
        for gone in ("getPlanSetup", "savePlanSetup", "addFixedCost", "deleteFixedCost"):
            assert gone not in api, gone

    def test_nothing_links_to_the_old_page(self):
        stale = [p.name for p in sorted(SRC.rglob("*.jsx"))
                 if re.search(r"""(onTab\??\.?\(|go\(|to=|dest: )['"](plan|piggy)['"]""",
                              p.read_text(encoding="utf-8"))]
        assert not stale, stale

    def test_onboarding_runs_the_check_before_the_path(self):
        """Linked → how Pearl uses your transactions (THL-117 CN-02) → the
        income and bills check → one last thing (CN-03) → Home."""
        text = (SRC / "pearl" / "Onboarding.jsx").read_text(encoding="utf-8")
        assert "<IncomeBillsFlow" in text
        assert "save({ step: 'uses' }, 'uses')" in text
        assert "step: 'income' },\n" in text and "'income');" in text
        assert "save({ step: 'email' }, 'email')" in text
        # CN-03's Finish ends onboarding on Home: the path went with Wins (2026-10-21).
        assert "saveOnboarding({ consents: { tips }, done: true })" in text
        assert "onDone?.('home')" in text and "placeOnPath" not in text


class TestHomeIsWhereTheAppLands:
    """Pearl THL-9 / THL-44 / THL-125: Home replaces the old landing tab, and
    the Allowance page's jobs move onto it (THL-166, THL-167)."""

    def test_the_app_opens_on_home(self):
        text = (SRC / "App.jsx").read_text(encoding="utf-8")
        # Cash flow's pages have addresses; anything else lands on Home.
        assert "readTxUrl() || isReviewUrl() || isInsightsUrl() || isCalendarUrl()" in text
        assert "? 'cashflow' : 'home'" in text
        assert "panel === 'home'" in text and "<HomePanel" in text
        # Home is bare (2026-10-21): the greeting, what needs a look, Transactions.
        home = (SRC / "panels" / "HomePanel.jsx").read_text(encoding="utf-8")
        assert "getHome()" in home and "<NeedsALook" in home and "onTab?.('transactions')" in home
        for gone in ("SafeToSpendCard", "PathCard", "CalendarStrip", "ForYou", "CarryoverPrompt"):
            assert gone not in home, gone

    def test_old_links_to_the_allowance_land_on_home(self, aliases):
        assert aliases.get("today") == "home"
        assert not (SRC / "panels" / "TodayPanel.jsx").exists()

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


class TestTheSidebarIsThl104s:
    def test_home_cash_flow_help_and_profile(self, groups):
        """The sidebar as the Pearl Handoff File draws it (2026-10-21): Home ·
        Cash flow, then Help and support · Profile at the foot. Save and Wins
        are gone for now."""
        assert list(groups) == ["home", "cashflow", "help", "profile"]

    def test_each_group_opens_on_its_first_page(self, groups):
        assert groups["home"] == ["home"]
        assert groups["cashflow"] == ["transactions", "calendar", "review", "insights", "budgets", "debts"]
        assert groups["help"] == ["protect"]
        for gone in ("overview", "growth", "transactions", "save", "wins"):
            assert gone not in groups, gone

class TestOneReviewQueue:
    def test_the_badge_counts_the_review_queue(self):
        text = (SRC / "App.jsx").read_text(encoding="utf-8")
        assert "getReview()" in text and "counts={{ cashflow: data.review }}" in text

    def test_review_holds_every_kind_and_the_unsorted_question(self):
        text = (SRC / "panels" / "NeedsALook.jsx").read_text(encoding="utf-8")
        for kind in ("unsorted", "money_in", "unsure_category", "income_type", "three_pay_month"):
            assert f"data.{kind}" in text, kind
        # Every kind is asked through the one sort card (THL-263).
        assert "<Stacked" in text and "from './Stacked.jsx'" in text
        app = (SRC / "App.jsx").read_text(encoding="utf-8")
        assert "<NeedsALook" in app and "ReviewPanel" not in app

    def test_rows_can_be_excluded_and_put_back(self):
        """One transaction at a time, from its detail; every one like it is a
        rule on Profile › Categories and rules (the old manager went with the
        prototype Projections page)."""
        tx = (SRC / "panels" / "TransactionDetail.jsx").read_text(encoding="utf-8")
        assert "excludeTransaction(" in tx and "includeTransaction(" in tx
        assert not (SRC / "panels" / "TransactionsPanel.jsx").exists()


class TestPearlTransactionsList:
    """THL-122: the Pearl list replaces Every charge, and its rules hold."""

    def test_the_group_opens_on_the_list(self):
        nav = (SRC / "nav.js").read_text(encoding="utf-8")
        assert "panels: ['transactions', 'calendar', 'review', 'insights', 'budgets', 'debts']" in nav
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
        # A guess reads "suggested by Pearl" and is dashed; a settled category
        # is filled (2026-10-21). The chip is just the word: the category's
        # icon is on the row's avatar, and a rule adds no lock (2026-10-22).
        assert "suggested by Pearl" in kit and "categoryIcon(label)" not in kit
        assert 'name="lock"' not in kit
        css = (SRC / "pearl" / "kit.css").read_text(encoding="utf-8")
        assert re.search(r"\.pk-cat\.suggested\s*\{[^}]*dashed", css)
        assert re.search(r"\.pk-cat\s*\{[^}]*border: 1px solid", css)


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
        # Change category is the sort card opened at "What was it for?" (THL-263).
        assert "<SortCard" in src and "step === 'category'" in src and "function ChangeCategory" not in src
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
        assert "MAX_PEOPLE = 50" in src

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


class TestTheProfileHub:
    """Pearl S-01: Profile is a hub; its pages carry a breadcrumb back to it
    instead of a sub-tab strip, and the old pages' links land on the new ones."""

    def test_the_group_opens_on_the_hub(self, groups):
        assert groups["profile"][0] == "profile"
        for key in ("accounts", "rules", "security", "income", "notifications", "consent",
                    "data"):
            assert key in groups["profile"], key

    def test_the_privacy_pages_are_wired(self, source):
        """THL-115, THL-116, THL-117, THL-139: the hub's You and Privacy rows
        open real pages, each works with an empty ledger, and none is left
        'Coming soon'."""
        hub = (SRC / "panels" / "ProfilePanel.jsx").read_text(encoding="utf-8")
        assert "soon: true" not in hub
        assert "doc: 'help'" in hub and "doc: 'legal'" in hub
        empty = _string_list(source, "WORKS_WHEN_EMPTY")
        for key in ("notifications", "consent", "data", "protect"):
            assert key in empty, key
        assert "<AccountDeleted" in source

    def test_the_choices_moved_to_privacy_and_consent(self):
        security = (SRC / "panels" / "SecurityPanel.jsx").read_text(encoding="utf-8")
        assert "Your choices" not in security and "saveOnboarding" not in security
        consent = (SRC / "panels" / "ConsentPanel.jsx").read_text(encoding="utf-8")
        assert "setConsent(" in consent and "<AiOffDialog" in consent
        onboarding = (SRC / "pearl" / "Onboarding.jsx").read_text(encoding="utf-8")
        assert "improve" not in onboarding

    def test_no_sub_tab_strip_for_profile(self, nav, source):
        assert "crumbs: true" in nav.split("key: 'profile'")[1].split("}")[0]
        assert "!group.crumbs" in source

    def test_old_keys_land_on_the_new_pages(self, aliases):
        assert aliases["account"] == "security"
        assert aliases["categories"] == "rules"
        assert aliases["banks"] == "accounts" and aliases["import"] == "accounts"
        assert not (SRC / "panels" / "AccountPanel.jsx").exists()

    def test_nothing_links_to_the_old_sign_in_page(self):
        stale = [p.name for p in sorted(SRC.rglob("*.jsx"))
                 if re.search(r"""(onTab\??\.?\(|go\()['"]account['"]""",
                              p.read_text(encoding="utf-8"))]
        assert not stale, stale

    def test_exclusions_moved_to_categories_and_rules(self):
        accounts = (SRC / "panels" / "AccountsPanel.jsx").read_text(encoding="utf-8")
        assert "ExclusionRules" not in accounts and "getExclusions" not in accounts
        rules = (SRC / "panels" / "RulesPanel.jsx").read_text(encoding="utf-8")
        assert "getRules()" in rules and "deleteRule(" in rules and "Always left out" in rules

    def test_the_email_changes_with_a_code(self):
        text = (SRC / "panels" / "SecurityPanel.jsx").read_text(encoding="utf-8")
        assert "startEmailChange(" in text and "verifyEmailChange(" in text
        assert "<CodeInput" in text

    def test_reconnect_opens_link_in_update_mode(self):
        text = (SRC / "panels" / "AccountsPanel.jsx").read_text(encoding="utf-8")
        assert "<ReconnectPanel" in text
        home = (SRC / "panels" / "HomePanel.jsx").read_text(encoding="utf-8")
        assert "createLinkToken(connection.item_id)" in home


class TestGrowthInsights:
    """THL-186 / THL-196 GR-28: Growth › Insights replaced the prototype
    Insights page, at an address of its own with one for each detail view."""

    def test_the_old_page_and_what_only_it_used_are_gone(self, panels, aliases):
        for path in ("panels/OverviewPanel.jsx", "components/Treemap.jsx",
                     "components/Ring.jsx", "categoryColors.js"):
            assert not (SRC / path).exists(), path
        assert "overview" not in panels and aliases["overview"] == "insights"
        api = (SRC / "api.js").read_text(encoding="utf-8")
        assert "getBreakdown" not in api and "/api/breakdown" not in api
        assert "getInsightsMonth" in api and "setMonthUnusual" in api

    def test_nothing_links_to_the_old_key(self):
        stale = [p.name for p in sorted(SRC.rglob("*.jsx"))
                 if re.search(r"""(onTab\??\.?\(|go\()['"]overview['"]""",
                              p.read_text(encoding="utf-8"))]
        assert not stale, stale

    def test_insights_has_an_address_and_draws_its_own_pills(self, source):
        router = (SRC / "router.js").read_text(encoding="utf-8")
        assert "INSIGHTS_PATH = '/cashflow/insights'" in router
        for view in ("month", "category", "subscriptions", "trend", "where", "money", "savings"):
            assert f"'{view}'" in router, view
        assert "isInsightsUrl()" in source and "writeInsightsUrl()" in source
        assert "OWN_SECTIONS = ['insights', 'calendar', 'budgets', 'debts', 'transactions', 'review']" in source
        assert "!ownSections" in source
        parts = (SRC / "panels" / "InsightsParts.jsx").read_text(encoding="utf-8")
        # Every page in a group is built: a group's pills are never disabled.
        tabs = parts[parts.index("export function GroupTabs"):]
        tabs = tabs[:tabs.index("</nav>")]
        assert "disabled" not in tabs and "g?.panels" in tabs

    def test_every_chart_has_a_table_for_a_screen_reader(self):
        charts = (SRC / "panels" / "InsightsCharts.jsx").read_text(encoding="utf-8")
        for name in ("TrendBars", "InOutBars", "CategoryBars", "SavingsArea", "IncomeBar"):
            body = charts[charts.index(f"export function {name}"):]
            body = body[:body.index("\n}\n")]
            assert "<ChartTable" in body, name
            assert 'aria-hidden="true"' in body, name
        pkg = json.loads((SRC.parent / "package.json").read_text(encoding="utf-8"))
        # Chart.js went with the prototype Projections page, its last user.
        # lottie-web plays "You earned a pearl" (THL-256), SVG renderer only.
        assert set(pkg["dependencies"]) == {"react", "react-dom", "lottie-web"}
        assert pkg["dependencies"]["lottie-web"] == "^5.12.2"


class TestNoPhaseNames:
    """THL-238 (2026-10-15): Pearl no longer uses named phases. Nothing she
    reads says Protect, Build, Unveil or Shine; the keys live on inside."""

    NAMES = re.compile(r"\b(Protect|Build|Unveil|Shine)\b")

    def _copy(self, text: str) -> list[str]:
        """Every string literal and JSX text node, comments stripped."""
        text = re.sub(r"\{/\*.*?\*/\}", "", text, flags=re.S)
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
        out = re.findall(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"|`((?:[^`\\]|\\.)*)`", text)
        strings = [a or b or c for a, b, c in out]
        strings += re.findall(r">([^<>{}]+)<", text)
        # Import paths and file names aren't copy.
        return [s for s in strings if not re.match(r"^\.{0,2}/|\.jsx?$", s.strip())]

    def test_nothing_she_reads_names_a_phase(self):
        hits = []
        for path in sorted(SRC.rglob("*.js*")):
            if ".test." in path.name:
                continue
            for s in self._copy(path.read_text(encoding="utf-8")):
                if self.NAMES.search(s):
                    hits.append(f"{path.relative_to(SRC)}: {s.strip()[:80]}")
        assert hits == [], "\n".join(hits)

    def test_the_path_and_the_welcome_email_are_milestones(self):
        from finance import emails, milestones
        for s in [*milestones.PHASE_LABELS.values(), *milestones.PHASE_TEXT.values(),
                  emails.TAGLINE, *[t for pair in emails.WELCOME_STEPS for t in pair]]:
            assert not self.NAMES.search(s), s


class TestCalendarAndQuickSort:
    """THL-255: the calendar is Cash flow's second tab at /cash-flow/calendar
    and Home's strip opens it. THL-254: the quick sort prompt is asked once
    the moments have had their turn."""

    def test_the_calendar_is_a_cash_flow_tab_with_an_address(self, source, nav):
        router = (SRC / "router.js").read_text(encoding="utf-8")
        assert "CALENDAR_PATH = '/cash-flow/calendar'" in router
        assert "[/^\\/cashflow\\/calendar$/, () => CALENDAR_PATH]" in router
        assert "'day'" in router                                   # the list's day filter
        assert "calendar:      { label: 'Calendar'" in nav
        assert "isCalendarUrl()" in source and "writeCalendarUrl()" in source
        assert "panel === 'calendar'" in source and "<CalendarPanel" in source
        panel = (SRC / "panels" / "CalendarPanel.jsx").read_text(encoding="utf-8")
        assert '<CashFlowTabs current="calendar"' in panel
        assert "bad" not in panel.lower().replace("badge", "")

    def test_quick_sort_is_offered_on_open(self, source):
        assert "getQuickSort()" in source and "<QuickSort" in source
        assert "askQuickSort()" in source
        # Its card is the sort card (THL-263): the same questions as Needs a look.
        qs = (SRC / "panels" / "QuickSort.jsx").read_text(encoding="utf-8")
        assert "<SortCard" in qs and "<SortedCard" in qs
        for words in ("Later", "Welcome back", "All sorted"):
            assert words in qs, words
        assert "Save and next" not in qs


def test_no_merge_conflict_markers_are_left_in_the_source():
    """A conflict resolved in GitHub's editor left `<<<<<<< HEAD` in nav.js
    (2026-10-15) and the deployment's build failed. Nothing ships with one."""
    root = SRC.parent
    marker = re.compile(r"^(<{7} |={7}$|>{7} )", re.M)
    found = []
    for folder in ("src", "finance", "tests"):
        for path in (root / folder).rglob("*"):
            if path.suffix not in (".js", ".jsx", ".css", ".py", ".json") or "node_modules" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if marker.search(text):
                found.append(str(path.relative_to(root)))
    for name in ("app.py", "vercel.json", "package.json"):
        if marker.search((root / name).read_text(encoding="utf-8")):
            found.append(name)
    assert not found, f"merge conflict markers left in: {found}"

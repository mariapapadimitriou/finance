import { useCallback, useEffect, useRef, useState } from 'react';
import HomePanel from './panels/HomePanel.jsx';
import InsightsPanel from './panels/InsightsPanel.jsx';
import PathPanel from './panels/PathPanel.jsx';
import LearnPanel from './panels/LearnPanel.jsx';
import { MomentScreen } from './panels/Moments.jsx';
import DebtsPanel from './panels/DebtsPanel.jsx';
import ProjectionsPanel from './panels/ProjectionsPanel.jsx';
import TransactionsList from './panels/TransactionsList.jsx';
import NeedsALook from './panels/NeedsALook.jsx';
import Goals from './panels/Goals.jsx';
import CategoryBudgetsPanel from './panels/CategoryBudgetsPanel.jsx';
import IncomeBillsPanel from './panels/IncomeBillsPanel.jsx';
import AccountsPanel from './panels/AccountsPanel.jsx';
import ProfilePanel from './panels/ProfilePanel.jsx';
import RulesPanel from './panels/RulesPanel.jsx';
import SecurityPanel from './panels/SecurityPanel.jsx';
import NotificationsPanel from './panels/NotificationsPanel.jsx';
import ConsentPanel from './panels/ConsentPanel.jsx';
import DataPanel, { AccountDeleted } from './panels/DataPanel.jsx';
import ProtectPanel from './panels/ProtectPanel.jsx';
import SignedOut, { resetTokenFromUrl, timeoutFromUrl, timeoutUrl } from './pearl/SignedOut.jsx';
import { DeviceApprovals, SessionTimeout } from './pearl/Session.jsx';
import Onboarding from './pearl/Onboarding.jsx';
import { Empty, ErrorNote, Loading } from './components/ui.jsx';
import Logo from './components/Logo.jsx';
import { ANCHORS, GROUPS, PANELS, resolve } from './nav.js';
import {
  clearUrl, fromPartner, isInsightsUrl, isLearnUrl, isPathUrl, isProjectionsUrl, isReviewUrl,
  readTxUrl, setGoalsIntent, writeInsightsUrl, writeLearnUrl, writePathUrl, writeProjectionsUrl,
  writeReviewUrl,
} from './router.js';
import {
  getAccounts, getAuthStatus, getCategories, getMoments, getReview, getSummary, logout,
  setLedgerCurrency, setUnauthorizedHandler, syncPlaid,
} from './api.js';

// Icons are 24×24 stroke paths, drawn in currentColor.

// Panels worth opening with nothing in the ledger: Accounts, where a bank is
// linked and which decides what keeps arriving — and which is also where the
// ledger gets emptied, so it is reachable immediately afterwards.
// The Profile hub and Sign-in and security too: a brand-new account has an
// empty ledger, and must still be able to change its email or sign out — and
// its notifications, consents and data (download, or delete the account).
// Goals too: someone new sees what comes next there (G-02). And Home, whose
// no-data state (E-01, THL-72) is where linking starts. Projections says what
// it can in words with nothing in, and holds Unveil's screens, which the Path
// links to. Learn is open to everyone from day one (THL-134).
const WORKS_WHEN_EMPTY = ['home', 'path', 'projections', 'learn', 'debts', 'budgets', 'accounts',
                          'income', 'profile', 'security', 'rules', 'goals', 'notifications',
                          'consent', 'data', 'protect'];

// Pages that draw their section pills themselves, under their own title
// (Growth › Path, THL-129 GR-01; Insights, THL-196 GR-28; Projections, THL-197
// GR-33; Learn, THL-134 GR-11), so the shell's strip would say it twice.
const OWN_SECTIONS = ['path', 'insights', 'projections', 'learn', 'budgets', 'debts'];

// Back from the partner (THL-136 GR-20) at any address: Ready to invest,
// where "Welcome back" asks whether she opened an account.
if (typeof window !== 'undefined' && fromPartner() && !isProjectionsUrl()) {
  window.history.replaceState(null, '', '/growth/ready?from=partner');
}

/**
 * A navigation label with an optional phone-width form.
 *
 * Both are rendered and CSS picks one, so the accessible name is always the
 * full label — a screen reader on a phone should still hear "Transactions".
 */
function Label({ full, short }) {
  if (!short) return full;
  return (
    <>
      <span className="label-full">{full}</span>
      <span className="label-short" aria-hidden="true">{short}</span>
    </>
  );
}

function Icon({ d }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

export default function App() {
  const [theme, setTheme] = useState(
    // A new key: the old one saved the old dark default on every visit, so
    // nobody would ever have seen the light default this introduced.
    () => localStorage.getItem('spendie-theme-2') || 'light'
  );
  // /transactions… opens the list (a link from anywhere lands there); every
  // other address opens Home, where the app lands (THL-44, THL-125).
  const [tab, setTab] = useState(() => (readTxUrl() || isReviewUrl() ? 'transactions'
    : isPathUrl() || isInsightsUrl() || isProjectionsUrl() || isLearnUrl() ? 'growth' : 'home'));
  const [panel, setPanel] = useState(() => (isReviewUrl() ? 'review'
    : readTxUrl() ? 'transactions' : isPathUrl() ? 'path' : isInsightsUrl() ? 'insights'
      : isProjectionsUrl() ? 'projections' : isLearnUrl() ? 'learn' : 'home'));

  /**
   * Go to a destination named either way.
   *
   * Panels link to each other by panel key — `onTab('income')` — and must not
   * have to know which group now owns it, so every one of those calls still
   * works unchanged.
   */
  const go = useCallback((key) => {
    const [group, target] = resolve(key);
    setTab(group);
    setPanel(target);
    // The list writes its own address when it mounts; Needs a look, Path,
    // Insights, Projections and Learn have one too. Everything else lives at "/". A
    // link straight to one of Insights' or Projections' views has already
    // written its address.
    if (target === 'review') writeReviewUrl();
    else if (target === 'path') writePathUrl();
    else if (target === 'insights') { if (!isInsightsUrl()) writeInsightsUrl(); }
    else if (target === 'projections') { if (!isProjectionsUrl()) writeProjectionsUrl(); }
    else if (target === 'learn') { if (!isLearnUrl()) writeLearnUrl(); }
    else if (target !== 'transactions') clearUrl();
    const anchor = ANCHORS[key];
    if (anchor) {
      // After the panel has rendered and its data has had a moment to land,
      // since what is being scrolled to is below a card that grows on load.
      setTimeout(() => {
        document.getElementById(anchor)
          ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 350);
    }
  }, []);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  // null while we're still asking; the app renders nothing rather than
  // flashing a dashboard at someone who then gets bounced to a login.
  const [signedIn, setSignedIn] = useState(null);
  // Who is signed in, for onboarding: a new account sets itself up before the
  // app opens. `fresh` is true straight after making one, which is when a
  // passkey is offered.
  const [user, setUser] = useState(null);
  const [fresh, setFresh] = useState(false);
  // THL-116 D-05: set once her account is deleted, shown until she closes it.
  const [deleted, setDeleted] = useState(null);
  // Bumped on every reload so panels that fetch their own data — Home,
  // Projections, Income and bills — refetch after an import instead of showing what
  // they loaded when they mounted.
  const [version, setVersion] = useState(0);
  // A phase done that she hasn't seen the moment for (THL-130 GR-08 to
  // GR-10), asked once per app open.
  const [moment, setMoment] = useState(null);
  const askedMoment = useRef(false);
  // A-14: signed out for being idle in this page's life, so signing back in
  // only needs the address put back; after a reload it needs a fresh load.
  const timedOut = useRef(false);
  const signOutIdle = useCallback(async () => {
    const here = window.location.pathname + window.location.search;
    await logout().catch(() => {});
    timedOut.current = true;
    window.history.replaceState(null, '', timeoutUrl(here));
    setData(null);
    setSignedIn(false);
  }, []);

  // Applied during render rather than in an effect, on purpose. Charts read
  // their colours from CSS custom properties when they build, and React runs
  // child effects before parent ones — so an effect here would set the theme
  // attribute *after* the charts had already sampled the outgoing theme,
  // leaving every chart one toggle behind.
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', theme);
  }

  useEffect(() => { localStorage.setItem('spendie-theme-2', theme); }, [theme]);

  // Back and forward between the list's addresses and the rest of the app.
  const panelRef = useRef(panel);
  panelRef.current = panel;
  useEffect(() => {
    const onPop = () => {
      if (isReviewUrl()) { setTab('transactions'); setPanel('review'); }
      else if (isPathUrl()) { setTab('growth'); setPanel('path'); }
      else if (isInsightsUrl()) { setTab('growth'); setPanel('insights'); }
      else if (isProjectionsUrl()) { setTab('growth'); setPanel('projections'); }
      else if (isLearnUrl()) { setTab('growth'); setPanel('learn'); }
      else if (readTxUrl()) { setTab('transactions'); setPanel('transactions'); }
      else if (['transactions', 'review', 'path', 'insights', 'projections', 'learn']
        .includes(panelRef.current)) {
        setTab('home'); setPanel('home');
      }
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  // A 401 from any request means the session went away — a password change,
  // or a cookie that expired while the tab sat open. Returning to the login
  // screen is better than every panel failing with its own error.
  useEffect(() => {
    setUnauthorizedHandler(() => setSignedIn(false));
  }, []);

  const checkAuth = useCallback(async () => {
    try {
      const s = await getAuthStatus();
      setUser(s.user ?? null);
      setSignedIn(s.signed_in);
      return s.signed_in;
    } catch (e) {
      setError(e);
      setSignedIn(false);
      return false;
    }
  }, []);

  useEffect(() => { checkAuth(); }, [checkAuth]);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [summary, accounts, categories, review] = await Promise.all([
        getSummary(), getAccounts(), getCategories(),
        // Only a badge: a failure here must not stop the app loading.
        getReview().catch(() => ({ count: 0 })),
      ]);
      // Before anything is drawn: every figure in the app is formatted with
      // this, and a wrong default is how the whole ledger came to read as
      // US dollars.
      setLedgerCurrency(summary.currency);
      setData({
        summary,
        accounts: accounts.accounts ?? [],
        categories: categories.categories ?? [],
        review: review.count ?? 0,
      });
      setVersion((v) => v + 1);
    } catch (e) {
      setError(e);
    }
  }, []);

  const onboarding = !!user && user.onboarding && !user.onboarding.done;

  useEffect(() => { if (signedIn && !onboarding) load(); }, [load, signedIn, onboarding]);

  // Pull from the banks as soon as the app opens, after the first paint so
  // the page never waits on Plaid. Once per sign-in; the figures reload only
  // if something actually came in, changed or went away. A failure is left
  // for Profile › Accounts to report.
  const synced = useRef(false);
  useEffect(() => {
    if (!signedIn || !data || synced.current) return;
    synced.current = true;
    syncPlaid()
      .then((r) => {
        const changed = (r?.imported ?? 0) > 0 || (r?.items ?? []).some(
          (i) => (i.modified ?? 0) > 0 || (i.removed ?? 0) > 0);
        if (changed) load();
      })
      .catch(() => {});
  }, [signedIn, data, load]);

  // Once the app has opened: a phase's moment plays once, full screen, on the
  // next open after it passes. Otherwise, if she went to the partner in the
  // last 14 days and hasn't said, Ready to invest asks (THL-136 GR-20).
  useEffect(() => {
    if (!signedIn || !data || askedMoment.current) return;
    askedMoment.current = true;
    getMoments().then((m) => {
      if (m.phase) setMoment(m);
      else if (m.partner_welcome && panelRef.current === 'home') {
        writeProjectionsUrl('ready');
        setTab('growth'); setPanel('projections');
      }
    }).catch(() => {});
  }, [signedIn, data]);

  if (signedIn === null) {
    return <Shell theme={theme} setTheme={setTheme}><Loading what="Pearl" /></Shell>;
  }

  if (deleted) {
    return <AccountDeleted sentTo={deleted.sentTo} onClose={() => setDeleted(null)} />;
  }

  // A reset link opens the reset screen even on a device that is signed in.
  if (!signedIn || resetTokenFromUrl()) {
    // A different person may be signing in on this device: nothing from the
    // last session's ledger is carried over.
    return <SignedOut onSignedIn={(u, { created = false } = {}) => {
      // A-15: back to the page she was on.
      const after = timeoutFromUrl();
      if (after && !timedOut.current) { window.location.replace(after.returnTo); return; }
      if (after) window.history.replaceState(null, '', after.returnTo);
      timedOut.current = false;
      setData(null);
      synced.current = false;
      setUser(u ?? null); setFresh(created);
      setSignedIn(true); setError(null);
    }} />;
  }

  if (onboarding) {
    const signOut = async () => { await logout(); setUser(null); setSignedIn(false); };
    return (
      <>
        <Onboarding user={user} startAt={fresh ? 'passkey' : null}
                    onSignOut={signOut}
                    onDone={(dest) => {
                      setFresh(false);
                      setUser((u) => ({ ...u, onboarding: { ...u.onboarding, done: true } }));
                      if (dest) go(dest);
                    }} />
        <SessionTimeout onTimeout={signOutIdle} onSignOut={signOut} />
      </>
    );
  }

  if (error) {
    return (
      <Shell theme={theme} setTheme={setTheme}>
        <div className="notice error" style={{ marginTop: 24 }}>
          <strong>Can&apos;t reach the Pearl API.</strong> {String(error.message)}
          <br />
          Start it with <code>python app.py</code> (or{' '}
          <code>flask --app app run</code>), then{' '}
          <button className="btn quiet" onClick={load}>retry</button>.
        </div>
      </Shell>
    );
  }

  if (!data) {
    return <Shell theme={theme} setTheme={setTheme}><Loading what="your spending" /></Shell>;
  }

  const { summary, accounts, categories } = data;

  if (moment) {
    return (
      <div className="gr-moment-page">
        <MomentScreen moment={moment} onClose={() => setMoment(null)} go={go}
                      toReady={() => { writeProjectionsUrl('ready'); go('projections'); }}
                      toAnchor={(view) => { setGoalsIntent({ view }); go('goals'); }} />
      </div>
    );
  }

  // An empty ledger hides the panels that have nothing to show — but not the
  // ones that exist to fix that, or this is a dead end: the Connect button
  // would set the tab and the same empty state would render over it, which
  // looks exactly like a button that does nothing.
  if (summary.empty && !WORKS_WHEN_EMPTY.includes(panel)) {
    return (
      <Shell theme={theme} setTheme={setTheme} tab={tab} panel={panel} onTab={go}>
        <Empty title="No spending yet">
          <div className="row" style={{ justifyContent: 'center', marginTop: 14 }}>
            <button className="btn primary" onClick={() => go('accounts')}>
              Link your bank
            </button>
          </div>
        </Empty>
      </Shell>
    );
  }

  const signOut = async () => { await logout(); setData(null); setSignedIn(false); };
  return (
    <>
    <SessionTimeout onTimeout={signOutIdle} onSignOut={signOut} />
    <DeviceApprovals />
    <Shell
      theme={theme} setTheme={setTheme} tab={tab} panel={panel} onTab={go}
      counts={{ transactions: data.review }}
      // The Pearl pages draw their own header (overline + title). Insights
      // has its own month switcher too (GR-28), so the shell picks no month.
      ownTitle={['home', 'path', 'insights', 'projections', 'learn', 'debts', 'budgets',
                 'transactions', 'review', 'goals', 'profile', 'accounts', 'rules', 'security',
                 'income', 'notifications', 'consent', 'data', 'protect'].includes(panel)}
      ownSections={OWN_SECTIONS.includes(panel)}
      onSignOut={signOut}
    >
      {panel === 'income' && <IncomeBillsPanel onTab={go} onChanged={load} version={version} />}
      {panel === 'home' && <HomePanel onTab={go} onChanged={load} version={version} />}
      {panel === 'path' && <PathPanel onTab={go} version={version} />}
      {panel === 'learn' && <LearnPanel onTab={go} version={version} />}
      {panel === 'debts' && <DebtsPanel onTab={go} onChanged={load} version={version} />}
      {panel === 'insights' && <InsightsPanel onTab={go} version={version} />}
      {panel === 'projections' && (
        <ProjectionsPanel onTab={go} onChanged={load} version={version} />
      )}
      {panel === 'review' && (
        <NeedsALook categories={categories} onChanged={load} onTab={go} version={version} />
      )}
      {panel === 'transactions' && (
        <TransactionsList summary={summary} categories={categories} accounts={accounts}
                          reviewCount={data.review} onTab={go} onChanged={load}
                          version={version} />
      )}
      {panel === 'goals' && (
        <Goals onTab={go} onChanged={load} version={version} />
      )}
      {panel === 'budgets' && (
        <CategoryBudgetsPanel onTab={go} onChanged={load} version={version} />
      )}
      {panel === 'profile' && <ProfilePanel onTab={go} version={version} />}
      {panel === 'accounts' && <AccountsPanel onChanged={load} onTab={go} version={version} />}
      {panel === 'rules' && (
        <RulesPanel categories={categories} onTab={go} onChanged={load} version={version} />
      )}
      {panel === 'notifications' && <NotificationsPanel onTab={go} version={version} />}
      {panel === 'consent' && <ConsentPanel onTab={go} version={version} />}
      {panel === 'protect' && <ProtectPanel onTab={go} version={version} />}
      {panel === 'data' && (
        <DataPanel onTab={go} onDeleted={(info) => {
          // Signed out on the server already; nothing of hers stays on screen.
          setData(null); setUser(null); synced.current = false;
          setDeleted(info); setSignedIn(false); go('home');
        }} />
      )}
      {panel === 'security' && (
        <SecurityPanel onTab={go} onSignOut={signOut} />
      )}
    </Shell>
    </>
  );
}

function Shell({ theme, setTheme, tab, panel, onTab, counts = {}, onSignOut,
                 ownTitle = false, ownSections = false, children }) {
  const group = GROUPS.find((g) => g.key === tab);
  // The heading names the panel you are actually looking at; the group label is
  // already on the selected button in the sidebar, so repeating it here would
  // say the same word twice and name the narrower thing nowhere.
  const current = PANELS[panel] ?? group;
  const navRef = useRef(null);
  const sectionsRef = useRef(null);

  // On a phone the nav is a scrolling strip, and twelve destinations don't
  // fit. Without this, opening the app on a tab that sits off the right edge
  // shows a bar with nothing selected in it.
  useEffect(() => {
    const selected = navRef.current?.querySelector('[aria-selected="true"]');
    // A hidden tab has no button in the strip; leaving it where it is beats
    // scrolling to a destination the reader did not choose.
    selected?.scrollIntoView({ inline: 'center', block: 'nearest',
                               behavior: 'smooth' });
  }, [tab]);

  // The section strip scrolls on a phone too, and opening Looking ahead used
  // to leave the strip reading "come & commitments | Budgets | Looking ahead":
  // the first tab sliced in half, and no hint that anything was there.
  // `nearest` moves it only as far as needed, and the strip's scroll-padding
  // keeps the chosen tab off the very edge.
  useEffect(() => {
    const selected = sectionsRef.current?.querySelector('[aria-selected="true"]');
    selected?.scrollIntoView({ inline: 'nearest', block: 'nearest' });
  }, [panel]);

  // Theme and sign-out, drawn twice: in the sidebar on a desktop and in the
  // top bar on a phone. On a phone they used to share the bottom bar with the
  // six destinations, which left no room for two of them.
  const accountActions = (
    <>
      {onSignOut && (
        <button className="btn quiet" onClick={onSignOut}
                aria-label="Sign out">
          <span aria-hidden="true">⎋</span>
          <span className="label">Sign out</span>
        </button>
      )}
      <button
        className="btn quiet"
        onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
      >
        <span aria-hidden="true">{theme === 'dark' ? '☀' : '☾'}</span>
        <span className="label">{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
      </button>
    </>
  );

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <Logo size={34} />
          <div className="name">pearl</div>
        </div>

        {onTab && (
          <nav className="nav" role="tablist" aria-orientation="vertical"
               ref={navRef}>
            {GROUPS.map((g) => (
              <button
                key={g.key}
                className={g.foot ? 'nav-foot' : undefined}
                role="tab"
                aria-selected={tab === g.key}
                // The group's first page: Transactions opens on To review.
                onClick={() => onTab(g.panels[0])}
              >
                <Icon d={g.icon} />
                <Label full={g.label} short={g.short} />
                {counts[g.key] > 0 && (
                  <span className="count" aria-label={`${counts[g.key]} to sort`}>
                    {counts[g.key]}
                  </span>
                )}
              </button>
            ))}
          </nav>
        )}

        <div className="sidebar-foot">{accountActions}</div>
      </aside>

      <div className="content">
        <div className="topbar">
          <div className="topbar-inner">
            <div className="title">
              {!ownTitle && <h1>{current?.label ?? 'Pearl'}</h1>}
            </div>

            <div className="topbar-actions">{accountActions}</div>
          </div>

          {group && group.panels.length > 1 && !group.crumbs && !ownSections && (
            <div className="sections-wrap">
            <nav className="sections" role="tablist" ref={sectionsRef}
                 aria-label={`${group.label} sections`}>
              {group.panels.map((key) => (
                <button
                  key={key}
                  role="tab"
                  aria-selected={panel === key}
                  onClick={() => onTab(key)}
                >
                  <Label full={PANELS[key].label} short={PANELS[key].short} />
                </button>
              ))}
            </nav>
            </div>
          )}
        </div>
        <main>{children}</main>
      </div>
    </div>
  );
}

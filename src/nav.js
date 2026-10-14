// Where everything is, and what it is called.
//
// One module, imported by the shell that draws the navigation and by the
// panels that link across it.

// Every panel the app can show, keyed the way it always was.
//
// These used to be twelve top-level destinations plus a hidden one, which on a
// phone was a scrolling strip nobody could hold in their head, and which put
// the four surfaces you touch once at setup beside the two you open daily.
// They are grouped below instead. The keys are unchanged, so every
// `onTab('piggy')` in a panel still works — `resolve` turns a panel key into
// the group that now contains it.
export const PANELS = {
  // Home (Pearl THL-125, GR-05): safe to spend for the month and how it was
  // worked out. Where the app lands.
  home:          { label: 'Home',
                   hint: 'What’s safe to spend this month, and how we worked it out' },
  // Growth › Budgets (THL-168 B-01): every category, from her usual month.
  budgets:       { label: 'Budgets',
                   hint: 'A budget for every category, starting at your usual month' },
  // Growth › Path (THL-129 GR-01): Protect, Build, Unveil and the next step.
  path:          { label: 'Path',
                   hint: 'Where you are on your path, and the one next step' },
  // Growth › Insights (THL-186, THL-196 GR-28, at /growth/insights): the
  // month against her usual, in pictures, with a detail view behind each.
  insights:      { label: 'Insights',
                   hint: 'Your month against your usual, and where the money went' },
  // Growth › Debts (THL-49 D-02): every balance owed, from before Pearl too.
  debts:         { label: 'Debts',
                   hint: 'Everything you owe, and the minimums counted as bills' },
  // Growth › Projections (THL-197 GR-33, at /growth/projections): this
  // month, the next 30 days and savings in a year, each as a range, and the
  // growth calculator (THL-135). Unveil's screens (GR-16, GR-37, GR-10) live
  // under it too.
  // Growth › Learn (THL-134 GR-11, at /growth/learn): five short modules
  // before investing, and two explainers. Open to everyone from day one.
  learn:         { label: 'Learn',
                   hint: 'Short reads on the basics of investing, at your pace' },
  projections:   { label: 'Projections',
                   hint: 'Where this month, the next 30 days and your savings are heading' },
  review:        { label: 'To review', short: 'Review',
                   hint: 'Everything Pearl isn’t sure about, with its best guess' },
  transactions:  { label: 'All transactions', short: 'All',
                   hint: 'Search, filter and check every transaction' },
  // Profile (Pearl S-01): the hub, and the pages it opens. Each Profile page
  // draws a breadcrumb back to the hub instead of a sub-tab strip.
  profile:       { label: 'Profile',
                   hint: 'Your accounts, rules, sign-in and privacy' },
  // Profile › Accounts (THL-120, AM-01): linking a bank through Plaid,
  // signing in to one again and syncing live here since Connections went (C1).
  accounts:      { label: 'Accounts',
                   hint: 'Your accounts, how each one counts, and linking a bank' },
  // Profile › Categories and rules (S-03): the rules she saved.
  rules:         { label: 'Categories and rules',
                   hint: 'The rules Pearl sorts by, and what you leave out' },
  // Profile › Sign-in and security, with S-02 (change the sign-in email).
  security:      { label: 'Sign-in and security',
                   hint: 'Your email, passkeys and signing out' },
  // Profile › Income and bills (THL-45, THL-127): the pay and regular bills
  // she confirmed after linking, and the check run again. It replaced the
  // prototype "Income & commitments" page and its piggy banks. `short` is
  // what a phone shows where the full label will not fit.
  income:        { label: 'Income and bills', short: 'Income',
                   hint: 'What comes in, and the regular bills set aside' },
  // Profile › Notifications (THL-139 N-02): which nudges, and how.
  notifications: { label: 'Notifications',
                   hint: 'Payday, weekly check-in, progress and milestones' },
  // Profile › Privacy and consent (THL-117 CN-04, CN-05).
  consent:       { label: 'Privacy and consent',
                   hint: 'What you’ve agreed to, and how to change it' },
  // Profile › Your data (THL-116 D-01 to D-04): download a copy, or delete
  // the account.
  data:          { label: 'Your data',
                   hint: 'Download a copy or delete your account' },
  // Profile › How we protect you (THL-115 T-04, with T-02 and T-03).
  protect:       { label: 'How we protect you',
                   hint: 'What Pearl can and can’t do' },
  goals:         { label: 'Goals',
                   hint: 'Your Anchor, your treasure chests and your saving goal' },
};

// The sidebar (Pearl THL-104, as every Handoff frame draws it): Home,
// Transactions, Goals and Growth, with Profile at the foot. A group holding
// one panel shows no sub-navigation.
export const GROUPS = [
  // Home replaces the old landing tab (THL-9, THL-44, THL-125): the page
  // people open the app for, so it is first and where the app lands.
  { key: 'home', label: 'Home', panels: ['home'],
    hint: 'What’s safe to spend this month',
    icon: 'M3 10.5 12 3l9 7.5M5 9v11h5v-6h4v6h5V9' },
  // Opens on the list (Pearl TX-01); what needs a look is one tap away, and
  // the list's alert links there too.
  { key: 'transactions', label: 'Transactions', short: 'Charges',
    panels: ['transactions', 'review'],
    hint: 'Every transaction, and what needs a look',
    icon: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01' },
  // The Anchor (the emergency fund, and the Build phase), treasure chests and
  // the saving goal (Pearl Handoff, THL-131/132/179). One page: the Anchor's
  // detail, its projection and each chest open inside it.
  { key: 'goals', label: 'Goals', panels: ['goals'],
    hint: 'Your Anchor, your treasure chests and your saving goal',
    icon: 'M12 21C16.9706 21 21 16.9706 21 12C21 7.02944 16.9706 3 12 3C7.02944 3 3 7.02944 3 12C3 16.9706 7.02944 21 12 21ZM12 17C14.7614 17 17 14.7614 17 12C17 9.23858 14.7614 7 12 7C9.23858 7 7 9.23858 7 12C7 14.7614 9.23858 17 12 17ZM12 13C12.5523 13 13 12.5523 13 12C13 11.4477 12.5523 11 12 11C11.4477 11 11 11.4477 11 12C11 12.5523 11.4477 13 12 13Z' },
  // Growth (THL-129 GR-01): Path, Insights, Projections and Learn, with
  // Budgets and Debts beside them (THL-9 decision N1). Each page draws these
  // as its own pills (GrowthTabs).
  { key: 'growth', label: 'Growth',
    panels: ['path', 'insights', 'projections', 'learn', 'budgets', 'debts'],
    hint: 'Where your money went, where it could go, and your budgets',
    icon: 'M3 17l6-6 4 4 8-8M15 7h6v6' },
  // At the foot (THL-104, Pearl S-01): the Profile hub, and the pages it
  // opens — Accounts, Categories and rules, Sign-in and security, Income and
  // bills, Notifications and the three Privacy pages — each with
  // a breadcrumb back to it, so the group shows no sub-tab strip (`crumbs`).
  { key: 'profile', label: 'Profile',
    panels: ['profile', 'accounts', 'rules', 'security', 'income', 'notifications', 'consent',
             'data', 'protect'], foot: true, crumbs: true,
    hint: 'Your accounts, rules, sign-in and privacy',
    icon: 'M20 21a8 8 0 0 0-16 0M12 13a5 5 0 1 0 0-10 5 5 0 0 0 0 10z' },
];

// Keys that are no longer panels of their own but are still linked to from
// across the app and from the insights, which carry a tab name in their data.
// The Income and commitments page (`plan`) became Income and bills (THL-127);
// its piggy banks are Goals' treasure chests, so a link to them lands there.
// The Mortgage page is gone: its payments are read from your accounts now,
// and a mortgage payment is a regular bill.
// The old landing tab and the old Settings group still resolve, so any link
// or saved address that names them lands somewhere real. So do the pages
// removed in C1: Connections and From a file land on Accounts, where a bank is
// linked now; Trips on the list; Categories on Categories and rules (S-03).
// The old Sign-in page is Sign-in and security now. The prototype Insights
// page (`overview`) was replaced by Growth › Insights (THL-196 GR-28).
export const ALIASES = {
  plan: 'income', piggy: 'goals', mortgage: 'income', today: 'home', settings: 'profile',
  banks: 'accounts', import: 'accounts', categories: 'rules',
  account: 'security', signin: 'security', overview: 'insights',
};

// Where on that page the aliased thing actually is, when it isn't the top.
// Without this a link lands at the top of a long page with no sign of what it
// pointed at, which is indistinguishable from a button that did nothing.
export const ANCHORS = {};

/**
 * Turn a group key or a panel key into both.
 *
 * Panels link to each other by panel key and should not have to know about the
 * grouping, so this accepts either: 'settings' opens the group at its first
 * panel, 'income' opens the same group at that panel.
 */
export function resolve(key) {
  const target = ALIASES[key] ?? key;
  // A page wins over a group of the same name: `transactions` is the list
  // itself, which is also the page its group opens on.
  const owner = GROUPS.find((g) => g.panels.includes(target));
  if (owner) return [owner.key, target];
  const group = GROUPS.find((g) => g.key === target);
  if (group) return [group.key, group.panels[0]];
  return ['home', 'home'];
}

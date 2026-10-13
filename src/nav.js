// Where everything is, and what it is called.
//
// One module, imported by the shell that draws the navigation and by every
// component that names a destination in a sentence. It used to live inside
// App.jsx, which meant a panel saying "sync on the Banks tab" had no way to
// ask what the tab was now called — and it went on saying Banks for months
// after the tab became Connections, inside a group called Cards & data.

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
  // `short` is what a phone shows where the full label will not fit. Only
  // set where it is needed; everything else uses its label at every width.
  plan:          { label: 'Income & commitments', short: 'Income',
                   hint: 'What comes in, what is spoken for, and what is left' },
  budgets:       { label: 'Budgets',
                   hint: 'Spent against budget, projected to month end' },
  // Growth › Path (THL-129 GR-01): Protect, Build, Unveil and the next step.
  path:          { label: 'Path',
                   hint: 'Where you are on your path, and the one next step' },
  // Growth › Insights (THL-129 GR-01's tabs): where the month's money went.
  overview:      { label: 'Insights',
                   hint: 'Spending across every card' },
  // Growth › Debts (THL-49 D-02): every balance owed, from before Pearl too.
  debts:         { label: 'Debts',
                   hint: 'Everything you owe, and the minimums counted as bills' },
  projections:   { label: 'Projections',
                   hint: 'What saving more gets you — this year, and invested' },
  review:        { label: 'To review', short: 'Review',
                   hint: 'Everything Pearl isn’t sure about, with its best guess' },
  transactions:  { label: 'All transactions', short: 'All',
                   hint: 'Search, filter and check every transaction' },
  trips:         { label: 'Trips',
                   hint: 'Date ranges whose spending counts as Travel' },
  banks:         { label: 'Connections',
                   hint: 'Connect a card through Plaid and let it sync itself' },
  accounts:      { label: 'Accounts',
                   hint: 'Every account, what syncs, and anything counted twice' },
  import:        { label: 'From a file', short: 'Files',
                   hint: "Statements for a card that can't be connected" },
  goals:         { label: 'Goals',
                   hint: 'Your Anchor, your treasure chests and your saving goal' },
  account:       { label: 'Sign-in',
                   hint: 'Who is signed in, and the password' },
  categories:    { label: 'Categories',
                   hint: 'Which categories share one line in your budget' },
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
    panels: ['transactions', 'review', 'trips'],
    hint: 'Every transaction, what needs a look, and your trips',
    icon: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01' },
  // The Anchor (the emergency fund, and the Build phase), treasure chests and
  // the saving goal (Pearl Handoff, THL-131/132/179). One page: the Anchor's
  // detail, its projection and each chest open inside it.
  { key: 'goals', label: 'Goals', panels: ['goals'],
    hint: 'Your Anchor, your treasure chests and your saving goal',
    icon: 'M12 21C16.9706 21 21 16.9706 21 12C21 7.02944 16.9706 3 12 3C7.02944 3 3 7.02944 3 12C3 16.9706 7.02944 21 12 21ZM12 17C14.7614 17 17 14.7614 17 12C17 9.23858 14.7614 7 12 7C9.23858 7 7 9.23858 7 12C7 14.7614 9.23858 17 12 17ZM12 13C12.5523 13 13 12.5523 13 12C13 11.4477 12.5523 11 12 11C11.4477 11 11 11.4477 11 12C11 12.5523 11.4477 13 12 13Z' },
  // Growth (THL-129 GR-01): Path, Insights, Projections and Learn, with
  // Budgets and Debts beside them (THL-9 decision N1). Learn isn't designed
  // yet.
  { key: 'growth', label: 'Growth', panels: ['path', 'overview', 'projections', 'budgets', 'debts'],
    hint: 'Where your money went, where it could go, and your budgets',
    icon: 'M3 17l6-6 4 4 8-8M15 7h6v6' },
  // At the foot (THL-104): accounts and connections (THL-120's Profile ›
  // Accounts), income and commitments until the confirmation flow (THL-45)
  // replaces it, files, categories (THL-9 decision N2) and sign-in.
  { key: 'profile', label: 'Profile',
    panels: ['accounts', 'banks', 'plan', 'import', 'categories', 'account'], foot: true,
    hint: 'Your accounts, income, categories and sign-in',
    icon: 'M20 21a8 8 0 0 0-16 0M12 13a5 5 0 1 0 0-10 5 5 0 0 0 0 10z' },
];

// Keys that are no longer panels of their own but are still linked to from
// across the app and from the insights, which carry a tab name in their data.
// Piggy banks are a card on the Plan page now — they are already a term in its
// arithmetic — so a link to them is a link there.
// The Mortgage page is gone: its payments are read from your accounts now.
// The old landing tab and the old Settings group still resolve, so any link
// or saved address that names them lands somewhere real.
export const ALIASES = { piggy: 'plan', mortgage: 'plan', today: 'home', settings: 'profile' };

// Where on that page the aliased thing actually is. Without this a link to a
// piggy bank lands at the top of a long page with no sign of one, which is
// indistinguishable from a button that did nothing.
export const ANCHORS = { piggy: 'piggy-banks' };

// What an alias is called in a sentence, since it has no panel label of its
// own to borrow.
const ALIAS_LABELS = { piggy: 'Piggy banks' };

/**
 * Turn a group key or a panel key into both.
 *
 * Panels link to each other by panel key and should not have to know about the
 * grouping, so this accepts either: 'settings' opens the group at its first
 * panel, 'import' opens the same group at that panel.
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

/**
 * What to call a destination in running text, from wherever you are.
 *
 * Inside the same group, the section name is enough — you can see the
 * switcher. From anywhere else it is the sidebar's word and then the
 * section's, because the section name alone ("Connections") is not something
 * you can find in the sidebar.
 */
export function destination(key, fromPanel) {
  const [groupKey, panelKey] = resolve(key);
  const group = GROUPS.find((g) => g.key === groupKey);
  const section = ALIAS_LABELS[key] ?? PANELS[panelKey]?.label ?? group?.label;
  const here = fromPanel && resolve(fromPanel)[0] === groupKey;

  if (!group) return section;
  if (here || group.panels.length === 1 || section === group.label) return section;
  return `${group.label} → ${section}`;
}

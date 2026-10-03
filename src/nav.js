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
  today:         { label: 'Today',
                   hint: 'What you can spend today, and why that number' },
  // `short` is what a phone shows where the full label will not fit. Only
  // set where it is needed; everything else uses its label at every width.
  plan:          { label: 'Income & commitments', short: 'Income',
                   hint: 'What comes in, what is spoken for, and what is left' },
  budgets:       { label: 'Budgets',
                   hint: 'Spent against budget, projected to month end' },
  overview:      { label: 'This month',
                   hint: 'Spending across every card' },
  projections:   { label: 'Looking ahead',
                   hint: 'What saving more gets you — this year, and invested' },
  savings:       { label: 'What to cut',
                   hint: 'Ranked by what it saves, with the charges behind it' },
  subscriptions: { label: 'Subscriptions',
                   hint: 'Every recurring charge found in your history' },
  transactions:  { label: 'Every charge',
                   hint: 'Searchable, correctable, chargeable to a piggy bank' },
  trips:         { label: 'Trips',
                   hint: 'Date ranges whose spending counts as Travel' },
  banks:         { label: 'Connections',
                   hint: 'Connect a card through Plaid and let it sync itself' },
  accounts:      { label: 'Accounts',
                   hint: 'Every account, what syncs, and anything counted twice' },
  import:        { label: 'From a file',
                   hint: "Statements for a card that can't be connected" },
  categories:    { label: 'Categories',
                   hint: 'Which categories share one line in your budget' },
};

// The six destinations. A group holding one panel shows no sub-navigation.
//
// A group's label is what the sidebar says, so it has to be what you find
// when you click it. "Overview" opened a page titled This month; "Savings"
// opened What to cut and Subscriptions — neither of them savings — while the
// figure you actually save sat under Plan. The keys stay as they were, so
// every link and every insight that names one still resolves.
export const GROUPS = [
  { key: 'today', label: 'Today', panels: ['today'],
    hint: 'What you can spend today, and why that number',
    icon: 'M12 8v4l3 2M12 22a10 10 0 1 1 0-20 10 10 0 0 1 0 20z' },
  // Looking ahead sits with the plan, not with the history: it is the plan
  // run forward, and the savings figure it offers to move is the plan's.
  { key: 'plan', label: 'Plan', panels: ['plan', 'budgets', 'projections'],
    hint: 'What you earn, what it is promised to, how the rest divides, and where that leads',
    icon: 'M3 3v18h18M7 15l4-4 3 3 5-6' },
  { key: 'overview', label: 'This month', short: 'Month', panels: ['overview'],
    hint: 'Where the money went',
    icon: 'M4 20V10M10 20V4M16 20v-7M22 20H2' },
  { key: 'savings', label: 'Cut back', panels: ['savings', 'subscriptions'],
    hint: 'What to cut, and the renewals worth a second look',
    icon: 'M12 3v18M17 7H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6' },
  { key: 'transactions', label: 'Transactions', short: 'Charges',
    panels: ['transactions', 'trips'],
    hint: 'Every charge, and the date ranges that reclassify them',
    icon: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01' },
  // Everything you set once and then leave: where the transactions come from,
  // and how the categories are grouped for budgeting. Neither is somewhere
  // you go to find out how the month is going.
  { key: 'settings', label: 'Settings',
    panels: ['banks', 'accounts', 'import', 'categories'],
    hint: 'Where the transactions come from, and how categories are grouped',
    icon: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z' },
];

// Keys that are no longer panels of their own but are still linked to from
// across the app and from the insights, which carry a tab name in their data.
// Piggy banks are a card on the Plan page now — they are already a term in its
// arithmetic — so a link to them is a link there.
export const ALIASES = { piggy: 'plan' };

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
  const group = GROUPS.find((g) => g.key === target);
  if (group) return [group.key, group.panels[0]];
  const owner = GROUPS.find((g) => g.panels.includes(target));
  if (owner) return [owner.key, target];
  return ['today', 'today'];
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

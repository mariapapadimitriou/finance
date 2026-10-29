// Joint accounts on screen (finance/joint.py).

/** "Who put this in?": Me, then each person she shares the account with —
 * or the account's label when she hasn't named them. */
export function depositChoices(people, label) {
  const named = (people ?? []).filter(Boolean);
  return [
    { value: 'me', who: 'me', person: null, label: 'Me',
      description: 'My own money: a transfer, not income' },
    ...(named.length ? named : [label || 'The other person']).map((name) => ({
      value: named.length ? `p:${name}` : 'them', who: 'them', person: named.length ? name : null,
      label: name,
      description: `Pays for ${name}’s part of this month’s joint spending`,
    })),
  ];
}

/** "Sam, Alex" → ["Sam", "Alex"]: trimmed, no repeats. */
export function parsePeople(text) {
  const out = [];
  for (const raw of String(text || '').split(/[,;\n]|\band\b/i)) {
    const name = raw.trim().replace(/\s+/g, ' ');
    if (name && !out.some((n) => n.toLowerCase() === name.toLowerCase())) out.push(name);
  }
  return out;
}

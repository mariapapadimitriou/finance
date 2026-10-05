// A soft gradient for each spending category.
//
// Keyed by the category's name, never by its rank in a month: Dining is the
// same colour whether it is this month's biggest block or its smallest, so a
// colour learned once stays true. Names are always written beside or on the
// colour, which is what lets ten hues cover thirty categories.

const PALETTE = [
  ['#a7b6df', '#b9c9ef'],   // periwinkle
  ['#6f86c6', '#8aa3e0'],   // deep periwinkle
  ['#c983bc', '#dfa0d2'],   // rose
  ['#a993d6', '#c2b0e8'],   // lilac
  ['#79b2bf', '#97cbd5'],   // teal
  ['#e0a184', '#efbba2'],   // peach
  ['#93b993', '#afcfae'],   // sage
  ['#cfb27a', '#e2c897'],   // sand
  ['#8a94a8', '#a6afc1'],   // slate
  ['#b08ab8', '#c8a5cf'],   // mauve
];

function hash(name) {
  let h = 0;
  for (let i = 0; i < name.length; i += 1) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return h;
}

export function categoryColors(name) {
  return PALETTE[hash(name || 'Other') % PALETTE.length];
}

export function categoryGradient(name) {
  const [a, b] = categoryColors(name);
  return `linear-gradient(160deg, ${a}, ${b})`;
}

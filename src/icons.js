// Category and merchant iconography.
//
// With ~30 spending categories, colour cannot keep them apart — past about
// eight hues nothing is distinguishable, especially under colour-vision
// deficiency. So identity is carried by an emoji badge plus the written label,
// and colour is left free to encode magnitude. It also makes the thing
// pleasant to scan, which is most of the point.

export const CATEGORY_ICON = {
  'Groceries': '🛒',
  'Dining': '🍽️',
  'Food Delivery': '🛵',
  'Coffee': '☕',
  'Alcohol & Bars': '🍸',
  'Transport': '🚊',
  'Gas & Fuel': '⛽',
  'Travel': '✈️',
  'Lodging': '🏨',
  'Shopping': '🛍️',
  'Streaming': '📺',
  'News & Media': '📰',
  'Software': '💻',
  'Utilities': '💡',
  'Phone & Internet': '📶',
  'Rent & Housing': '🏠',
  'Insurance': '🛡️',
  'Health': '💊',
  'Fitness': '🏋️',
  'Personal Care': '💅',
  'Entertainment': '🎟️',
  'Education': '📚',
  'Pets': '🐾',
  'Home': '🛋️',
  'Gifts & Charity': '🎁',
  'Fees & Interest': '🧾',
  'Taxes': '🏛️',
  'Cash & ATM': '💵',
  'Income': '💰',
  'Transfers': '🔄',
  'Other': '❓',
};

export function categoryIcon(category) {
  return CATEGORY_ICON[category] ?? '💳';
}

// Findings are grouped by how much work they take, not by category.
export const EFFORT_ICON = {
  'one-off': '⚡',
  'habit': '🔁',
  'negotiate': '📞',
};

export function effortIcon(effort) {
  return EFFORT_ICON[effort] ?? '💡';
}

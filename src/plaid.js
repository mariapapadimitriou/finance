// Plaid Link, loaded from Plaid's CDN rather than bundled.
//
// Plaid require the script to be loaded from their domain so fixes and
// institution changes reach every integration without a redeploy — a bundled
// copy would go stale against banks that change their login. Loaded on demand
// rather than at page load, so nothing is fetched from Plaid until a bank is
// actually being linked.

const LINK_SCRIPT = 'https://cdn.plaid.com/link/v2/stable/link-initialize.js';

export function loadPlaidScript() {
  if (window.Plaid) return Promise.resolve(window.Plaid);
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${LINK_SCRIPT}"]`);
    if (existing) {
      existing.addEventListener('load', () => resolve(window.Plaid));
      existing.addEventListener('error', () => reject(new Error('Plaid Link failed to load.')));
      return;
    }
    const tag = document.createElement('script');
    tag.src = LINK_SCRIPT;
    tag.onload = () => resolve(window.Plaid);
    tag.onerror = () => reject(new Error('Plaid Link failed to load.'));
    document.head.appendChild(tag);
  });
}

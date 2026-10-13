import { afterEach, describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  ApprovalPrompt, Refused, SIGN_OUT_AFTER, TimeoutWarning, WARN_AFTER, clockWords, idlePhase,
  spokenLeft,
} from './Session.jsx';
import { deviceWord, timeoutFromUrl, timeoutUrl, usedWords } from './SignedOut.jsx';
import { RecoveryCodes, SecurityPage } from '../panels/SecurityPanel.jsx';

const html = (el) => renderToStaticMarkup(el);

describe('session timeout (A-14)', () => {
  it('warns at 14 minutes and signs out at 15', () => {
    expect(idlePhase(WARN_AFTER - 1)).toEqual({ phase: 'active', left: null });
    expect(idlePhase(WARN_AFTER)).toEqual({ phase: 'warn', left: 60 });
    expect(idlePhase(WARN_AFTER + 2.5)).toEqual({ phase: 'warn', left: 58 });
    expect(idlePhase(SIGN_OUT_AFTER)).toEqual({ phase: 'out', left: 0 });
  });

  it('counts down as A-14 draws it, and speaks only at 30 and 10 seconds', () => {
    expect(clockWords(58)).toBe('0:58');
    expect(clockWords(60)).toBe('1:00');
    expect(spokenLeft(58)).toBe('');
    expect(spokenLeft(30)).toBe('30 seconds left');
    expect(spokenLeft(29)).toBe('30 seconds left');            // unchanged, so not said again
    expect(spokenLeft(10)).toBe('10 seconds left');
  });

  it('is an alert dialog with "Stay signed in" first', () => {
    const out = html(<TimeoutWarning left={58} onStay={() => {}} onSignOut={() => {}} />);
    expect(out).toContain('role="alertdialog"');
    expect(out).toContain('Still there?');
    expect(out).toContain('You’ve been inactive for a while, so we’ll sign you out soon to keep your money private.');
    expect(out).toContain('0:58');
    expect(out.indexOf('Stay signed in')).toBeLessThan(out.indexOf('Sign out now'));
  });
});

describe('signed out (A-15)', () => {
  const at = (url) => {
    const u = new URL(url, 'https://pearl.example');
    globalThis.window = { location: { pathname: u.pathname, search: u.search } };
  };
  afterEach(() => { delete globalThis.window; });

  it('knows where she was', () => {
    at(timeoutUrl('/transactions?category=Dining'));
    expect(timeoutFromUrl()).toEqual({ returnTo: '/transactions?category=Dining' });
  });

  it('never sends her anywhere off the site', () => {
    for (const bad of ['//evil.example', 'https://evil.example', '/\\evil.example', '/sign-in']) {
      at(timeoutUrl(bad));
      expect(timeoutFromUrl()).toEqual({ returnTo: '/' });
    }
  });

  it('only on /sign-in, for a timeout', () => {
    at('/sign-in');
    expect(timeoutFromUrl()).toBeNull();
    at('/?reason=timeout');
    expect(timeoutFromUrl()).toBeNull();
  });
});

describe('a new device (A-07, A-08)', () => {
  it('says where to look', () => {
    expect(deviceWord('Safari on iPhone')).toBe('phone');
    expect(deviceWord('Chrome on Android')).toBe('phone');
    expect(deviceWord('Safari on iPad')).toBe('iPad');
    expect(deviceWord('Chrome on Mac')).toBe('other device');
  });

  it('says when the other device was used', () => {
    const now = new Date(2026, 9, 9, 18, 0).getTime();
    expect(usedWords(new Date(2026, 9, 9, 8, 0).getTime() / 1000, now)).toBe('used today');
    expect(usedWords(new Date(2026, 9, 6, 8, 0).getTime() / 1000, now)).toBe('used Tuesday');
    expect(usedWords(new Date(2026, 8, 20, 8, 0).getTime() / 1000, now)).toBe('used Sep 20');
    expect(usedWords(null)).toBe('');
  });

  it('asks her signed-in device, naming the browser and where', () => {
    const out = html(<ApprovalPrompt approval={{ id: 1, label: 'Chrome on Mac', near: 'Toronto, ON' }}
                                     onAnswer={() => {}} onClose={() => {}} />);
    expect(out).toContain('Is this you signing in?');
    expect(out).toContain('Chrome on Mac, near Toronto, ON, just now.');
    expect(out.indexOf('Approve')).toBeLessThan(out.indexOf('This wasn’t me'));
    expect(html(<Refused onDone={() => {}} />)).toContain('We stopped that sign-in');
  });
});

describe('recovery codes', () => {
  it('are offered on Sign-in and security', () => {
    const none = html(<SecurityPage user={{ email: 'a@b.c', passkeys: 1, recovery_codes: 0 }} />);
    expect(none).toContain('Recovery codes');
    expect(none).toContain('Make codes');
    const some = html(<SecurityPage user={{ email: 'a@b.c', passkeys: 1, recovery_codes: 7 }} />);
    expect(some).toContain('7 of 10 left. Each works once.');
    expect(some).toContain('Make new ones');
  });

  it('new ones say the old stop working', () => {
    expect(html(<RecoveryCodes had={7} onClose={() => {}} />))
      .toContain('The codes you have now stop working');
    expect(html(<RecoveryCodes had={0} onClose={() => {}} />)).toContain('Make recovery codes');
  });
});

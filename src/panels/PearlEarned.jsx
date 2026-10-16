import { useEffect, useRef, useState } from 'react';
import { pearlMomentSeen } from '../api.js';
import { Dialog, PButton } from '../pearl/kit.jsx';
import logoMark from '../pearl/assets/logo-mark.svg';
import './pearl-earned.css';

/**
 * "You earned a pearl" (Pearl THL-112 EP-00 to EP-05; THL-256).
 *
 * Shown the first time she opens Pearl after earning a milestone, over
 * whatever page she lands on: a modal on the web, a bottom sheet on a
 * phone. Once per milestone, ever; several at once make one sheet ("You
 * earned 2 pearls") and the animation plays once.
 *
 * The animation is the Design System's Logo/Mark opening to reveal the
 * pearl (pearl-earned.json, 160×134, 60 fps, 96 frames), played by
 * lottie-web 5.12.2 with the SVG renderer and `loop: false`, so it rests
 * on the open mark. It is decorative (`aria-hidden`); focus goes to the
 * title, announced as "Pearl earned. <milestone>." No sound.
 *
 * Reduce Motion (EP-04): no Lottie, no sparkles, no haptic. The static
 * open mark, and the sheet fades in over 200 ms. The same still is the
 * fallback when the animation file can't be loaded.
 */
export const ANIMATION_URL = '/pearl-earned.json';

export function reduceMotion() {
  try {
    return !!window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
  } catch {
    return false;
  }
}

/** The mark: the Lottie when motion is welcome and the file loads, else the still. */
export function Mark({ still = false }) {
  const box = useRef(null);
  const [fallback, setFallback] = useState(still);
  useEffect(() => {
    if (still || !box.current) return undefined;
    let anim = null;
    let live = true;
    (async () => {
      try {
        const [{ default: lottie }, res] = await Promise.all([
          import('lottie-web/build/player/lottie_svg'),
          fetch(ANIMATION_URL),
        ]);
        // The SPA catch-all answers unknown paths with index.html and a 200,
        // so a missing file looks like HTML, not an error.
        if (!res.ok || !/json/.test(res.headers.get('content-type') || '')) throw new Error(`animation ${res.status}`);
        const animationData = await res.json();
        if (!live || !box.current) return;
        anim = lottie.loadAnimation({
          container: box.current, renderer: 'svg', loop: false, autoplay: true, animationData,
          rendererSettings: { preserveAspectRatio: 'xMidYMid meet', progressiveLoad: false },
        });
      } catch {
        if (live) setFallback(true);
      }
    })();
    return () => { live = false; anim?.destroy?.(); };
  }, [still]);
  return (
    <div className={`pe-mark${fallback ? ' still' : ''}`} aria-hidden="true">
      <span className="pe-halo" />
      {fallback
        ? <img src={logoMark} alt="" width="160" height="134" />
        : <div className="pe-lottie" ref={box} />}
    </div>
  );
}

export default function PearlEarned({ moment, onClose, onSeePearls }) {
  const still = reduceMotion();
  const keys = (moment?.pearls ?? []).map((p) => p.key);
  const title = useRef(null);

  // Shown means seen: once per milestone, ever (EP-01), whatever she does next.
  useEffect(() => {
    if (keys.length) pearlMomentSeen(keys).catch(() => {});
    const t = setTimeout(() => title.current?.focus(), 30);
    return () => clearTimeout(t);
  }, []);                                                   // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Dialog labelledBy="pe-title" describedBy="pe-line" onClose={onClose}
            className={`pe-sheet${still ? ' still' : ''}`}>
      <Mark still={still} />
      <p className="pk-overline pe-overline">{moment.overline}</p>
      <h2 className="pk-h2 pe-title" id="pe-title" tabIndex={-1} ref={title}
          aria-label={moment.announce || `${moment.overline}. ${moment.title}.`}>
        {moment.title}
      </h2>
      <p className="pk-muted pe-line" id="pe-line">{moment.line}</p>
      <div className="pe-actions">
        <PButton onClick={() => onSeePearls?.(keys)}>See your pearls</PButton>
        <PButton variant="text" onClick={onClose}>Done</PButton>
      </div>
    </Dialog>
  );
}

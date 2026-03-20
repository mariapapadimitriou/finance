import { useState, useRef } from 'react';
import { createPortal } from 'react-dom';

/**
 * InfoTooltip — renders via a React Portal into document.body so it is never
 * clipped by parent overflow:hidden or stacking context (e.g. .card).
 *
 * Positioning: uses getBoundingClientRect() + position:fixed so it sits 8px
 * above the ⓘ trigger regardless of scroll position or DOM nesting.
 */
export default function InfoTooltip({ text }) {
  const [visible, setVisible] = useState(false);
  const [rect, setRect]       = useState(null);
  const triggerRef            = useRef(null);

  const onEnter = () => {
    const r = triggerRef.current?.getBoundingClientRect();
    if (r) setRect(r);
    setVisible(true);
  };

  // Clamp horizontal position so tooltip never bleeds off-screen
  const tipWidth  = 230;
  const tipLeft   = rect ? Math.min(
    Math.max(rect.left + rect.width / 2, tipWidth / 2 + 8),
    window.innerWidth - tipWidth / 2 - 8
  ) : 0;

  // fixed bottom = distance from viewport bottom to trigger top, + 8px gap
  const tipBottom = rect ? window.innerHeight - rect.top + 8 : 0;

  const portal = (visible && rect)
    ? createPortal(
        <div style={{
          position:    'fixed',
          bottom:      tipBottom,
          left:        tipLeft,
          transform:   'translateX(-50%)',
          width:       tipWidth,
          background:  '#0d1520',
          border:      '1px solid #1e2f42',
          borderRadius: 4,
          padding:     '.55rem .7rem',
          fontSize:    '.62rem',
          color:       '#c8dff0',
          lineHeight:  1.65,
          zIndex:      9999,
          boxShadow:   '0 6px 24px rgba(0,0,0,.75)',
          pointerEvents: 'none',
          fontFamily:  "'IBM Plex Mono', monospace",
          fontWeight:  400,
          letterSpacing: '.02em',
          whiteSpace:  'normal',
        }}>
          {text}
          {/* caret pointing down toward the trigger */}
          <div style={{
            position:    'absolute',
            top:         '100%',
            left:        '50%',
            transform:   'translateX(-50%)',
            width: 0, height: 0,
            borderLeft:  '5px solid transparent',
            borderRight: '5px solid transparent',
            borderTop:   '5px solid #1e2f42',
          }} />
        </div>,
        document.body
      )
    : null;

  return (
    <span
      ref={triggerRef}
      style={{
        display:      'inline-flex',
        alignItems:   'center',
        marginLeft:   '.3rem',
        verticalAlign:'middle',
        cursor:       'default',
        flexShrink:   0,
      }}
      onMouseEnter={onEnter}
      onMouseLeave={() => setVisible(false)}
    >
      {/* ⓘ icon */}
      <span style={{
        fontSize:    '.56rem',
        fontFamily:  "'IBM Plex Mono', monospace",
        fontStyle:   'normal',
        color:       visible ? '#00d4ff' : '#2d4560',
        border:      `1px solid ${visible ? '#00d4ff' : '#172230'}`,
        borderRadius:'50%',
        width: 13, height: 13,
        display:     'inline-flex',
        alignItems:  'center',
        justifyContent: 'center',
        lineHeight:  1,
        userSelect:  'none',
        transition:  'color .12s, border-color .12s',
      }}>i</span>

      {portal}
    </span>
  );
}

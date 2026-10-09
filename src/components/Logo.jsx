// The Pearl mark: the open scallop with the pearl revealed, as exported from
// the Pearl Handoff File (Logo/Mark). Drawn at the design's 6:5 proportion.
import mark from '../pearl/assets/logo-mark.svg';

export default function Logo({ size = 34 }) {
  return (
    <img src={mark} width={Math.round(size * 1.2)} height={size} alt=""
         style={{ display: 'block' }} />
  );
}

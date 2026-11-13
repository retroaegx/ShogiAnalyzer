// 新規 → 手合割 (same positions as HANDICAP_SFEN in server/app/core/kifu_common.py, which names the
// handicap again from the start position on export); 平手 is the server's default start
const HANDICAP_TAIL = "/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL w - 1";
export const HANDICAPS = [
  ["平手", null],
  ["香落ち", "lnsgkgsn1/1r5b1"],
  ["右香落ち", "1nsgkgsnl/1r5b1"],
  ["角落ち", "lnsgkgsnl/1r7"],
  ["飛車落ち", "lnsgkgsnl/7b1"],
  ["飛香落ち", "lnsgkgsn1/7b1"],
  ["二枚落ち", "lnsgkgsnl/9"],
  ["三枚落ち", "lnsgkgsn1/9"],
  ["四枚落ち", "1nsgkgsn1/9"],
  ["五枚落ち", "2sgkgsn1/9"],
  ["左五枚落ち", "1nsgkgs2/9"],
  ["六枚落ち", "2sgkgs2/9"],
  ["左七枚落ち", "2sgkg3/9"],
  ["右七枚落ち", "3gkgs2/9"],
  ["八枚落ち", "3gkg3/9"],
  ["十枚落ち", "4k4/9"],
].map(([name, top]) => [name, top && top + HANDICAP_TAIL]);

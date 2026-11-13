// UI themes (表示設定 → テーマ): colours / background of the whole screen, defined in app.css
// under [data-theme]. The first one is the default. themeColor: the browser / app bar colour.
export const UI_THEMES = [
  { id: "sumikin", name: "墨金", themeColor: "#070a11" },
  { id: "aurora", name: "極光", themeColor: "#0d0a26" },
  { id: "emerald", name: "翠苑", themeColor: "#05150f" },
  { id: "sakura", name: "暁桜", themeColor: "#f6e2d6" },
  { id: "pearl", name: "白金", themeColor: "#f5f1e8" },
  { id: "frost", name: "蒼雪", themeColor: "#e8f1fb" },
];

export const THEME_NAMES = {
  "theme.bg.wood": "木目",
  "theme.bg.sansui": "山水",
  "theme.bg.fujitsuki": "藤月",
  "theme.bg.neon_night": "ネオン\u200bナイト", // \u200b: where the name may wrap in a small tile
  "theme.bg.white_gold": "ホワイト\u200bゴールド",
  "theme.piece.tsuge": "黄楊",
  "theme.piece.mokume": "杢目",
  "theme.piece.urushi": "漆黒",
  "theme.piece.black": "黒文字",
  "theme.piece.white": "白地",
};

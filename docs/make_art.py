"""Regenerate the README art (animated SVG, no scripts): python docs/make_art.py
生成 README 用的动画 SVG：banner-light.svg、banner-dark.svg、init-demo.svg。"""
from pathlib import Path
from xml.sax.saxutils import escape

DOCS = Path(__file__).resolve().parent

SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Noto Sans CJK SC', 'Microsoft YaHei', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', 'PingFang SC', 'Noto Sans Mono CJK SC', monospace"

SCRIBBLES = [
    ("M86 44c-2-12 12-20 22-14 9 6 6 19-4 21-9 2-14-8-8-13 5-4 12-1 11 4", "#e64980", 0.0),
    ("M82 36c8-12 28-12 34 0", "#12b886", 0.25),
    ("M90 22c6-6 16-3 17 4", "#fab005", 0.5),
    ("M80 50c8 8 26 8 34-2", "#7950f2", 0.75),
    ("M100 58c6 1 10-2 12-6", "#4dabf7", 1.0),
]


def cat(outline: str) -> str:
    """The logo, with the wand's scribble drawing itself in a loop and a twinkling hat star."""
    strokes = "".join(
        f'<path d="{d}" stroke="{c}" stroke-dasharray="130" stroke-dashoffset="130">'
        f'<animate attributeName="stroke-dashoffset" values="130;0;0;130" keyTimes="0;0.3;0.85;1" dur="5s" '
        f'begin="{b}s" repeatCount="indefinite"/></path>'
        for d, c, b in SCRIBBLES)
    return f'''
  <g fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-width="3.4">{strokes}</g>
  <path d="M50 88 L88 50" stroke="{outline}" stroke-width="7" stroke-linecap="round"/>
  <path d="M12 76c0-17 13-28 30-28s30 11 30 28c0 16-13 26-30 26S12 92 12 76z" fill="#8f8b84"/>
  <g fill="#f4f1ea"><ellipse cx="37.5" cy="86.5" rx="6" ry="4.6"/><ellipse cx="46.5" cy="86.5" rx="6" ry="4.6"/></g>
  <g fill="#8f8b84"><path d="M16 62l-4-16 14 9z"/><path d="M68 62l4-16-14 9z"/></g>
  <g fill="#f2cf3c"><circle cx="31" cy="73" r="6.5"/><circle cx="53" cy="73" r="6.5"/></g>
  <g fill="#1d1d1f"><ellipse cx="32" cy="73.5" rx="2.4" ry="4.6">
      <animate attributeName="ry" values="4.6;4.6;0.4;4.6;4.6" keyTimes="0;0.9;0.93;0.96;1" dur="6s" repeatCount="indefinite"/></ellipse>
    <ellipse cx="52" cy="73.5" rx="2.4" ry="4.6">
      <animate attributeName="ry" values="4.6;4.6;0.4;4.6;4.6" keyTimes="0;0.9;0.93;0.96;1" dur="6s" repeatCount="indefinite"/></ellipse></g>
  <path d="M39.2 81.6h5.6l-2.8 3.4z" fill="#e8849a"/>
  <path d="M14 58L38 8c2-4 6-4 8 0l26 50z" fill="#2f6fd6"/>
  <path d="M8 58c0-4 16-7 34-7s34 3 34 7-16 6-34 6S8 62 8 58z" fill="#1f56b0"/>
  <circle cx="44" cy="34" r="7" fill="#fff"/>
  <path d="M44 28.5l1.8 3.7 4 .6-2.9 2.8.7 4-3.6-1.9-3.6 1.9.7-4-2.9-2.8 4-.6z" fill="#2f6fd6">
    <animate attributeName="opacity" values="1;0.35;1" dur="2.4s" repeatCount="indefinite"/></path>'''


SPARKLE = "M0-10L2.4-2.4 10 0 2.4 2.4 0 10-2.4 2.4-10 0-2.4-2.4z"
SPARKLES = [(330, 62, 1.1, 2.6, 0.0), (1180, 70, 0.9, 3.1, 0.6), (1225, 250, 0.7, 2.2, 1.2), (56, 280, 0.8, 2.9, 0.3),
            (300, 300, 0.6, 2.4, 1.6), (720, 40, 0.55, 3.4, 0.9), (1010, 312, 0.75, 2.7, 0.2), (268, 170, 0.5, 2.0, 1.1)]


def banner(dark: bool) -> str:
    bg1, bg2 = ("#0d1526", "#1b1440") if dark else ("#eaf1ff", "#fdf0f6")
    ink, sub, accent = ("#f5f7fb", "#b8c2d6", "#7aa7ff") if dark else ("#1b2233", "#4a5568", "#2f6fd6")
    chip_bg, chip_ink = ("#ffffff14", "#dfe6f3") if dark else ("#ffffffcc", "#2c3a55")
    spark = "#ffd43b" if dark else "#f59f00"
    stars = "".join(
        f'<path d="{SPARKLE}" fill="{spark}" transform="translate({x} {y}) scale({s})" opacity="0.2">'
        f'<animate attributeName="opacity" values="0.15;1;0.15" dur="{d}s" begin="{b}s" repeatCount="indefinite"/></path>'
        for x, y, s, d, b in SPARKLES)
    chips, x = "", 400
    for label in ["Canvas → 1 page", "4× a day", "AES-256", "AI agent", "$0 · GitHub Actions", "English · 中文"]:
        w = 30 + sum(15 if ord(ch) > 0x2e80 else 8.6 for ch in label)
        chips += (f'<rect x="{x}" y="262" width="{w:.0f}" height="34" rx="17" fill="{chip_bg}" stroke="{accent}" '
                  f'stroke-opacity="0.35"/><text x="{x + w / 2:.0f}" y="284" text-anchor="middle" font-size="15" '
                  f'fill="{chip_ink}">{escape(label)}</text>')
        x += w + 10
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 360" width="1280" height="360" role="img" aria-label="Purrfessor · 喵教授: your Canvas day on one encrypted page">
  <title>Purrfessor · 喵教授</title>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{bg1}"/><stop offset="1" stop-color="{bg2}"/></linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="{accent}" stop-opacity="0.35"/><stop offset="1" stop-color="{accent}" stop-opacity="0"/></radialGradient>
  </defs>
  <rect width="1280" height="360" rx="28" fill="url(#bg)"/>
  <circle cx="200" cy="185" r="175" fill="url(#glow)"/>
  {stars}
  <g transform="translate(58 44) scale(2.2)">
    <g>
      <animateTransform attributeName="transform" type="translate" values="0 0;0 -3.5;0 0" dur="4s" repeatCount="indefinite"/>
      {cat(ink if dark else "#1d1d1f")}
    </g>
  </g>
  <g font-family="{SANS}">
    <text x="400" y="138" font-size="84" font-weight="800" fill="{ink}" letter-spacing="-1.5">Purrfessor</text>
    <text x="870" y="138" font-size="60" font-weight="700" fill="{accent}">喵教授</text>
    <text x="402" y="190" font-size="27" fill="{ink}">Your Canvas day, on one encrypted page.</text>
    <text x="402" y="230" font-size="23" fill="{sub}">每天一页：Canvas 上要做的事一目了然，AI 帮你排好先后。</text>
    {chips}
  </g>
</svg>
'''


# ---------- terminal demo of `purrfessor init` (made-up repo and name) ----------

G, W, D, R, C, Y, B = "#3fb950", "#e6edf3", "#8b949e", "#f85149", "#58a6ff", "#d29922", "#bc8cff"
LINES = [  # (seconds after start, [(text, color), …])
    (0.2, [("$ ", G), ("purrfessor init", W)]),
    (1.0, [("🧙🐱 Purrfessor · 喵教授 — setting up ", W), ("alex/my-today", C)]),
    (1.3, []),
    (1.5, [("School presets / 学校预设: generic, ucr", D)]),
    (2.2, [("Preset / 预设 [ucr]: ", W), ("↵", D)]),
    (3.0, [("Language / 语言 (zh = 中文, en = English) [zh]: ", W), ("en", Y)]),
    (3.8, [("Your name on the page / 页面上显示的名字 [Me]: ", W), ("Alex", Y)]),
    (4.2, [("  ✓ ", G), ("wrote purrfessor.toml (private — git-ignored)", W)]),
    (5.2, [("Canvas token (hidden / 不显示): ", W)]),
    (5.9, [("  ✓ ", G), ("Canvas: Alex Kim", W)]),
    (6.7, [("Site password / 网站口令 (hidden / 不显示): ", W)]),
    (7.3, [("Again / 再输一次: ", W)]),
    (8.1, [("Gemini API key (optional / 可选; hidden): ", W)]),
    (8.6, [("  ✓ ", G), ("secret ", W), ("CANVAS_TOKEN", B)]),
    (8.8, [("  ✓ ", G), ("secret ", W), ("SITE_PASSWORD", B)]),
    (9.0, [("  ✓ ", G), ("secret ", W), ("GEMINI_API_KEY", B)]),
    (9.2, [("  ✓ ", G), ("secret ", W), ("PURRFESSOR_CONFIG", B)]),
    (9.5, [("  ✓ ", G), ("variable ", W), ("PURRFESSOR_ENABLED=true", B)]),
    (9.9, [("  ✓ ", G), ("GitHub Pages → GitHub Actions", W)]),
    (10.4, [("  ✓ ", G), ("deploy started (takes ~3 min) / 已触发部署（约 3 分钟）", W)]),
    (10.7, []),
    (11.2, [("Your page / 你的页面: ", W), ("https://alex.github.io/my-today/", C), ("  🎉", W)]),
]
CYCLE, HOLD_END = 17.0, 16.3


def demo() -> str:
    lh, top, left = 22, 62, 24
    height = top + lh * len(LINES) + 40
    out = []
    for i, (t, parts) in enumerate(LINES):
        if not parts:
            continue
        a, b = t / CYCLE, HOLD_END / CYCLE
        spans = "".join(f'<tspan fill="{c}">{escape(s).replace(" ", chr(0xa0))}</tspan>' for s, c in parts)
        out.append(f'<text x="{left}" y="{top + i * lh}" opacity="0">{spans}'
                   f'<animate attributeName="opacity" values="0;0;1;1;0;0" keyTimes="0;{a:.4f};{a + 0.004:.4f};{b:.4f};{b + 0.02:.4f};1" '
                   f'dur="{CYCLE}s" repeatCount="indefinite"/></text>')
    cy = top + (len(LINES)) * lh - 15
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 860 {height}" width="860" height="{height}" role="img" aria-label="Terminal: purrfessor init asks a few questions, stores the GitHub secrets, turns on Pages and starts the first deploy">
  <title>purrfessor init</title>
  <rect width="860" height="{height}" rx="12" fill="#0d1117"/>
  <rect width="860" height="38" rx="12" fill="#161b22"/><rect y="26" width="860" height="12" fill="#161b22"/>
  <circle cx="22" cy="19" r="6.5" fill="#ff5f57"/><circle cx="44" cy="19" r="6.5" fill="#febc2e"/><circle cx="66" cy="19" r="6.5" fill="#28c840"/>
  <text x="430" y="24" text-anchor="middle" font-family="{SANS}" font-size="13" fill="{D}">purrfessor init — ~/my-today</text>
  <g font-family="{MONO}" font-size="14.5" style="white-space:pre">
    {chr(10).join("    " + x for x in out).strip()}
  </g>
  <rect x="{left}" y="{cy}" width="9" height="18" fill="{W}">
    <animate attributeName="opacity" values="1;0;1" dur="1s" repeatCount="indefinite"/></rect>
</svg>
'''


(DOCS / "banner-light.svg").write_text(banner(False), encoding="utf-8")
(DOCS / "banner-dark.svg").write_text(banner(True), encoding="utf-8")
(DOCS / "init-demo.svg").write_text(demo(), encoding="utf-8")
print("ok")

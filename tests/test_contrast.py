"""Small coloured text keeps 4.5:1 in light and dark mode (WCAG AA); the tick box border 3:1.
The page CSS mixes every Tabler colour toward black (white in dark mode); this recomputes the contrast of every colour
from the two numbers in the template, so nobody can lower the mix by accident. 浅色和深色模式下，小号彩色文字都在 4.5:1 以上。"""
from __future__ import annotations

import re

import pytest

from purrfessor.render import COLORS, HEX, TEMPLATE

# Tabler 1.6.1 palette as sRGB (its oklch values, read back in Chrome) and the card colour of each theme. A Tabler upgrade
# changes these: measure them again (getComputedStyle + a canvas read) and update here.
# Tabler 1.6.1 的调色板（oklch 转成 sRGB）和两种主题下卡片的颜色；升级 Tabler 之后要重新测。
PALETTE = {"red": "#d73938", "orange": "#f76707", "yellow": "#f59f00", "lime": "#74b816", "green": "#2eb345", "teal": "#0da679",
           "cyan": "#17a2b8", "azure": "#4299e1", "blue": "#066fd1", "indigo": "#4262ea", "purple": "#af3ec8",
           "pink": "#d7336d", "secondary": {"light": "#727372", "dark": "#a3a2a2"}}
CARD = {"light": "#fefeff", "dark": "#262626"}
WASH = 0.10        # a "-lt" badge is the colour at 10% over the card
ALERT_WASH = 0.08  # .alert-warning: the colour at 16%, mixed half way back into the card by Tabler
CSS = TEMPLATE.read_text(encoding="utf-8")


def rgb(h: str) -> list[float]:
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)]


def luminance(c) -> float:
    s = [v / 255 / 12.92 if v / 255 <= .03928 else ((v / 255 + .055) / 1.055) ** 2.4 for v in c]
    return .2126 * s[0] + .7152 * s[1] + .0722 * s[2]


def contrast(a, b) -> float:
    x, y = luminance(a), luminance(b)
    return (max(x, y) + .05) / (min(x, y) + .05)


def mix(a, b, share: float) -> list[float]:
    """color-mix(in srgb, a share, b)"""
    return [x * share + y * (1 - share) for x, y in zip(a, b)]


def tokens(scheme: str) -> tuple[str, float]:
    """(ink, share of the colour) as the template sets them; the dark block overrides the light one."""
    block = re.search(r':root\s*\{([^}]*)\}', CSS).group(1)
    if scheme == "dark":
        block += re.search(r':root\[data-bs-theme="dark"\]\s*\{([^}]*)\}', CSS).group(1)
    ink = re.findall(r"--tone-ink:\s*(#[0-9a-f]{3,6})", block)[-1]
    mix_ = re.findall(r"--tone-mix:\s*(\d+)%", block)[-1]
    return (ink + ink[1:] if len(ink) == 4 else ink), int(mix_) / 100


def base(name: str, scheme: str) -> str:
    c = PALETTE[name]
    return c[scheme] if isinstance(c, dict) else c


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("name", [*COLORS, "secondary"])
def test_badge_text_reaches_4_5(name, scheme):
    """Every course colour (and the grey of "later") on its own pale wash."""
    ink, share = tokens(scheme)
    colour, card = rgb(base(name, scheme)), rgb(CARD[scheme])
    text, wash = mix(colour, rgb(ink), share), mix(colour, card, WASH)
    assert contrast(text, wash) >= 4.5, (name, scheme, contrast(text, wash))


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("name", COLORS)
def test_next_class_number_reaches_4_5(name, scheme):
    """The big "starts in …" number keeps its course hue (the calendar's hex colour) mixed toward the ink; it sits on the card."""
    ink, share = tokens(scheme)
    assert "#next-class .next-big { color: color-mix(in srgb, var(--c, var(--tblr-body-color)) var(--tone-mix), var(--tone-ink))" in CSS
    assert contrast(mix(rgb(HEX[name]), rgb(ink), share), rgb(CARD[scheme])) >= 4.5


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_deadline_alert_reaches_4_5(scheme):
    """The yellow box that shows a deadline found in an announcement (it was 2.0:1 in light mode)."""
    ink, share = tokens(scheme)
    colour, card = rgb(base("yellow", scheme)), rgb(CARD[scheme])
    assert contrast(mix(colour, rgb(ink), share), mix(colour, card, ALERT_WASH)) >= 4.5


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_tick_box_border_reaches_3(scheme):
    assert re.search(r"\.tick \{[^}]*border: 2px solid var\(--tick-line\)", CSS)
    assert "--tick-line: var(--tblr-secondary)" in CSS
    assert contrast(rgb(base("secondary", scheme)), rgb(CARD[scheme])) >= 3


def test_every_badge_colour_has_a_tone_rule():
    """A colour without its `--tone` line would silently keep Tabler's low-contrast text."""
    for name in [*COLORS, "secondary"]:
        assert f".badge.bg-{name}-lt" in CSS, name


def test_finished_items_are_faded_with_colour_not_opacity():
    """opacity .5 on a title was 2.6:1; the done title uses the secondary text colour (and keeps its strike-through)."""
    done = re.search(r"\.task\.done \.title, \.task\.checked \.title \{([^}]*)\}", CSS).group(1)
    assert "opacity" not in done and "var(--tblr-secondary-color)" in done and "line-through" in done
    for opacity in re.findall(r"\.(?:cls\.past|task\.checked \.cd) \{ opacity: ([\d.]+)", CSS):
        assert float(opacity) >= .7        # faded, but not below 3:1

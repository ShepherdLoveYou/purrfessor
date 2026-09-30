"""Settings = a public school preset (presets/*.toml) merged with a private personal config (purrfessor.toml).
设置 = 公开的学校预设（presets/*.toml）+ 私密的个人配置（purrfessor.toml），个人配置优先。

The personal config is kept out of the (public) repo and passed to CI as the PURRFESSOR_CONFIG secret.
个人配置不进公开仓库，通过 GitHub Secret PURRFESSOR_CONFIG 传给 CI。
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

PKG = Path(__file__).resolve().parent
PRESETS = PKG / "presets"
LANGUAGES = ("zh", "en")


@dataclass
class Settings:
    school: str
    canvas_url: str
    tz: ZoneInfo
    language: str = "en"
    name: str = "Me"
    preset: str = "generic"
    banner: dict = field(default_factory=dict)
    term: dict = field(default_factory=dict)
    courses: dict = field(default_factory=dict)       # Canvas course id → display name
    notes: list = field(default_factory=list)
    classes: list = field(default_factory=list)
    recurring: list = field(default_factory=list)
    features: dict = field(default_factory=dict)
    site: dict = field(default_factory=dict)           # [site] path / home: where the page is published
    warnings: list = field(default_factory=list)       # i18n keys

    @property
    def translate(self) -> bool:
        """Chinese UI → translate English Canvas content. English UI → nothing to translate.
        中文界面才需要把英文的 Canvas 内容翻译成中文。"""
        return self.language == "zh" and self.features.get("translate", True)

    def on(self, feature: str) -> bool:
        return bool(self.features.get(feature, True))

    @property
    def page_path(self) -> str:
        """[site] path = "today" → "today/": the page is published at <site>/today/. "" = the site root."""
        p = str(self.site.get("path", "")).strip("/")
        if p and (not re.fullmatch(r"[A-Za-z0-9._/-]+", p) or any(x in ("", ".", "..") for x in p.split("/"))):
            raise ValueError(f"[site] path = {p!r}: use letters, digits, '-', '_' and '/' only")
        return f"{p}/" if p else ""


def merge(base: dict, over: dict) -> dict:
    """Deep-merge dicts; lists and scalars from `over` replace those in `base`."""
    out = dict(base)
    for k, v in over.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def presets() -> list[str]:
    return sorted(p.stem for p in PRESETS.glob("*.toml"))


def load(path: str | Path | None) -> Settings:
    warnings = []
    user: dict = {}
    if path and Path(path).exists():
        with open(path, "rb") as f:
            user = tomllib.load(f)
    else:
        warnings.append("warn_no_config")
    preset_name = user.get("preset", "generic")
    preset_path = PRESETS / f"{preset_name}.toml"
    preset: dict = {}
    if preset_path.exists():
        with open(preset_path, "rb") as f:
            preset = tomllib.load(f)
    else:
        warnings.append("warn_unknown_preset")
    cfg = merge(preset, user)
    school = cfg.get("school", {})
    language = cfg.get("language", "en")
    return Settings(
        school=school.get("name", "My School"),
        canvas_url=school.get("canvas_url", "https://canvas.instructure.com").rstrip("/"),
        tz=ZoneInfo(school.get("timezone", "America/New_York")),
        language=language if language in LANGUAGES else "en",
        name=cfg.get("name", "Me"),
        preset=preset_name,
        banner=cfg.get("banner", {}),
        term=cfg.get("term", {}),
        courses={int(k): v for k, v in cfg.get("courses", {}).items()},
        notes=cfg.get("notes", []),
        classes=cfg.get("classes", []),
        recurring=cfg.get("recurring", []),
        features={"agent": True, "meme": True, "grades": True, "translate": True, **cfg.get("features", {})},
        site=cfg.get("site", {}),
        warnings=warnings,
    )

"""Config = public school preset + private personal config. 配置 = 学校预设 + 个人配置。"""
from __future__ import annotations

import tomllib

from purrfessor import cli, config


def write(tmp_path, text):
    p = tmp_path / "purrfessor.toml"
    p.write_text(text, encoding="utf-8")
    return p


def test_presets_ship_with_the_package():
    assert {"ucr", "generic"} <= set(config.presets())


def test_personal_config_overrides_preset(tmp_path):
    S = config.load(write(tmp_path, 'preset = "ucr"\nlanguage = "zh"\nname = "A"\n[term]\nholidays = ["2027-01-01"]\n'
                                     '[school]\nname = "UCR"\n'))
    assert S.school == "UCR" and S.canvas_url == "https://elearn.ucr.edu"          # deep merge keeps the rest
    assert str(S.tz) == "America/Los_Angeles" and S.banner["url"].startswith("https://registrationssb.ucr.edu")
    assert S.term["holidays"] == ["2027-01-01"]                                     # lists are replaced
    assert S.translate and S.on("agent") and S.warnings == []


def test_english_never_translates(tmp_path):
    S = config.load(write(tmp_path, 'preset = "ucr"\nlanguage = "en"\n'))
    assert S.language == "en" and not S.translate


def test_unknown_language_falls_back_to_english(tmp_path):
    assert config.load(write(tmp_path, 'language = "fr"\n')).language == "en"


def test_missing_config_and_unknown_preset_warn(tmp_path):
    assert config.load(tmp_path / "nope.toml").warnings == ["warn_no_config"]
    S = config.load(write(tmp_path, 'preset = "nowhere"\n'))
    assert S.warnings == ["warn_unknown_preset"] and S.canvas_url == "https://canvas.instructure.com"


def test_generic_preset_has_no_banner(tmp_path):
    S = config.load(write(tmp_path, 'preset = "generic"\n[school]\ncanvas_url = "https://canvas.example.edu/"\n'))
    assert not S.banner.get("url") and S.canvas_url == "https://canvas.example.edu"


def test_example_config_is_valid_and_loads(tmp_path):
    text = cli.EXAMPLE.read_text(encoding="utf-8")
    tomllib.loads(text)
    S = config.load(write(tmp_path, text))
    assert S.warnings == [] and S.school == "UC Riverside" and S.language == "zh"


def test_init_template_substitution(tmp_path):
    text = cli.EXAMPLE.read_text(encoding="utf-8")
    for needle in ('preset = "ucr"', 'language = "zh"', 'name = "Alex"'):
        assert needle in text, needle                     # cli.init replaces these lines

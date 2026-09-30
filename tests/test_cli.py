"""`purrfessor init` and the workflow helpers, with gh and the prompts faked. init 与工作流辅助命令（gh 和输入都是假的）。"""
from __future__ import annotations

import hashlib
import json

import pytest

from purrfessor import cli, config


class FakeGH:
    """Records every gh call; answers `repo view`, `secret list` and `api …/pages`."""

    def __init__(self, secrets=(), pages="", template=False):
        self.secrets, self.pages, self.template, self.calls, self.set = list(secrets), pages, template, [], {}

    def __call__(self, *args, stdin=None, check=True):
        self.calls.append(args)
        if args[:2] == ("repo", "view"):
            return "someone/my-today"
        if args[:2] == ("secret", "list"):
            return "\n".join(self.secrets)
        if args[:2] == ("secret", "set"):
            self.set[args[2]] = stdin
        if args[0] == "api" and "--jq" in args:
            return self.pages if args[1].endswith("/pages") else str(self.template).lower()
        return ""


def typed(answers):
    """A fake prompt: the next answer, then EOFError like a real terminal after Ctrl-D."""
    answers = iter(answers)

    def prompt(_=""):
        try:
            return next(answers)
        except StopIteration:
            raise EOFError from None
    return prompt


@pytest.fixture
def run_init(tmp_path, monkeypatch, capsys):
    def run(answers, secrets_typed, gh=None):
        gh = gh or FakeGH()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(cli.shutil, "which", lambda _: "/usr/bin/gh")
        monkeypatch.setattr(cli, "gh", gh)
        monkeypatch.setattr(cli, "gh_ok", lambda *a: gh(*a) == "" and True)
        monkeypatch.setattr(cli, "canvas_whoami", lambda base, token: "Test Student" if token == "good" else None)
        monkeypatch.setattr("builtins.input", typed(answers))
        monkeypatch.setattr(cli.getpass, "getpass", typed(secrets_typed))
        cli.main(["init"])
        return gh, capsys.readouterr().out
    return run


def test_init_on_a_fresh_copy(run_init, tmp_path):
    # preset, language, name · token (a bad one first), password twice, no Gemini key
    gh, out = run_init(["ucr", "en", "Sam"], ["bad", "good", "pw1", "pw1", ""])
    assert gh.set == {"CANVAS_TOKEN": "good", "SITE_PASSWORD": "pw1",
                      "PURRFESSOR_CONFIG": (tmp_path / "purrfessor.toml").read_text(encoding="utf-8")}
    S = config.load(tmp_path / "purrfessor.toml")
    assert (S.preset, S.language, S.name, S.school) == ("ucr", "en", "Sam", "UC Riverside")
    assert ("variable", "set", "PURRFESSOR_ENABLED", "-R", "someone/my-today", "--body", "true") in gh.calls
    assert ("api", "-X", "POST", "repos/someone/my-today/pages", "-f", "build_type=workflow") in gh.calls
    assert ("workflow", "run", "deploy.yml", "-R", "someone/my-today") in gh.calls
    assert "token doesn't work" in out and "✓ Canvas: Test Student" in out
    assert out.rstrip().endswith("https://someone.github.io/my-today/  🎉")


def test_init_generic_school(run_init, tmp_path):
    gh, out = run_init(["generic", "State U", "https://canvas.state.edu", "America/Chicago", "zh", "Lin"],
                       ["good", "pw", "pw", "gem"])
    S = config.load(tmp_path / "purrfessor.toml")
    assert (S.school, S.canvas_url, S.tz.key, S.language) == ("State U", "https://canvas.state.edu", "America/Chicago", "zh")
    assert gh.set["GEMINI_API_KEY"] == "gem"
    assert "[term]" in out   # reminder to fill in the term dates and classes


def test_init_again_keeps_existing_secrets_and_config(run_init, tmp_path):
    """Re-running init (or moving an existing site over): Enter keeps every secret; the config is reused."""
    (tmp_path / "purrfessor.toml").write_text('preset = "ucr"\nlanguage = "zh"\nname = "W"\n[site]\npath = "today"\n',
                                              encoding="utf-8")
    gh = FakeGH(secrets=["CANVAS_TOKEN", "SITE_PASSWORD", "GEMINI_API_KEY"], pages="workflow")
    gh, out = run_init([""], ["", "", ""], gh)
    assert list(gh.set) == ["PURRFESSOR_CONFIG"]          # nothing else was overwritten
    assert not any(c[:2] == ("api", "-X") for c in gh.calls)   # Pages already on
    assert "保留现有 token" in out and "保留现有口令" in out
    assert out.rstrip().endswith("https://someone.github.io/my-today/today/  🎉")


def test_init_cannot_skip_a_secret_that_is_not_set(run_init):
    """Without an existing token, Enter is not accepted; same for the password."""
    gh, out = run_init(["ucr", "zh", "A"], ["", "good", "", "pw", "pw", ""])
    assert gh.set["CANVAS_TOKEN"] == "good" and gh.set["SITE_PASSWORD"] == "pw"


def test_init_refuses_the_template_itself(run_init):
    gh = FakeGH(template=True)
    with pytest.raises(SystemExit, match="template"):
        run_init([], [], gh)
    assert not gh.set


def test_init_stops_cleanly_on_ctrl_d(run_init):
    with pytest.raises(SystemExit, match="Cancelled"):
        run_init(["ucr", "zh", "A"], [])      # getpass hits the end of input


def test_your_repo_is_origin_even_with_an_upstream_remote(tmp_path, monkeypatch):
    """After `git remote add upstream <template>`, gh would pick the template; init must still use origin."""
    import subprocess
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:someone/my-today.git"], check=True)
    subprocess.run(["git", "remote", "add", "upstream", "https://github.com/ShepherdLoveYou/purrfessor.git"], check=True)
    monkeypatch.setattr(cli, "gh", FakeGH())
    assert cli.your_repo() == "someone/my-today"


# ---------- ci-env: page location and salt for the workflow ----------

def ci_env(tmp_path, monkeypatch, capsys, conf, base="https://someone.github.io/my-today"):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "purrfessor.toml").write_text(conf, encoding="utf-8")
    cli.main(["ci-env", "--config", "purrfessor.toml", "--base-url", base, "--repo-id", "123"])
    out = capsys.readouterr()
    return dict(line.split("=", 1) for line in out.out.splitlines()), out.err


def test_ci_env_site_root(tmp_path, monkeypatch, capsys):
    env, _ = ci_env(tmp_path, monkeypatch, capsys, 'preset = "ucr"\n')
    assert env == {"SALT": hashlib.sha256(b"purrfessor-123").hexdigest()[:32], "PAGE": "",
                   "PAGE_URL": "https://someone.github.io/my-today/", "ARCHIVE_BASE": "/my-today/archive/",
                   "HOME_URL": ""}


def test_ci_env_subpath_with_home_link(tmp_path, monkeypatch, capsys):
    env, _ = ci_env(tmp_path, monkeypatch, capsys, '[site]\npath = "/today/"\nhome = true\n')
    assert (env["PAGE"], env["PAGE_URL"], env["ARCHIVE_BASE"], env["HOME_URL"]) == (
        "today/", "https://someone.github.io/my-today/today/", "/my-today/today/archive/", "/my-today/")


def test_ci_env_user_site_at_domain_root(tmp_path, monkeypatch, capsys):
    env, _ = ci_env(tmp_path, monkeypatch, capsys, '[site]\npath = "today"\nhome = true\n',
                    base="https://someone.github.io")
    assert (env["PAGE_URL"], env["ARCHIVE_BASE"], env["HOME_URL"]) == (
        "https://someone.github.io/today/", "/today/archive/", "/")


def test_ci_env_warns_when_the_dashboard_would_replace_a_home_page(tmp_path, monkeypatch, capsys):
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "index.html").write_text("home")
    _, err = ci_env(tmp_path, monkeypatch, capsys, "")
    assert "::warning::" in err


def test_salt_from_staticrypt_json_wins(tmp_path):
    (tmp_path / ".staticrypt.json").write_text(json.dumps({"salt": "0123456789abcdef0123456789abcdef"}))
    assert cli.site_salt("123", tmp_path / ".staticrypt.json") == "0123456789abcdef0123456789abcdef"
    (tmp_path / ".staticrypt.json").write_text(json.dumps({"salt": "not-a-salt"}))
    assert cli.site_salt("123", tmp_path / ".staticrypt.json") == hashlib.sha256(b"purrfessor-123").hexdigest()[:32]


@pytest.mark.parametrize("path", ["../up", "a//b", "a b", "./x", "<script>"])
def test_bad_site_paths_are_rejected(tmp_path, path):
    (tmp_path / "c.toml").write_text(f'[site]\npath = "{path}"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        config.load(tmp_path / "c.toml").page_path

"""purrfessor — command line. 命令行。

  purrfessor init             one-time setup in your copy of the template (asks a few questions, sets GitHub secrets)
                              一次性配置：回答几个问题，自动设置 GitHub Secrets、开启 Pages、触发第一次部署
  purrfessor build ...        build the page (same as python -m purrfessor.build)
  purrfessor config-upload    after editing purrfessor.toml: upload it as the PURRFESSOR_CONFIG secret and redeploy
  purrfessor snapshot ...     used by the workflow (fetch / add)
  purrfessor lock-args        used by the workflow: Staticrypt password-page texts in the configured language

Secrets are read with getpass (never echoed) and handed to `gh secret set` on stdin. 口令和 token 不回显，经 stdin 交给 gh。
"""
from __future__ import annotations

import getpass
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from .config import PKG, presets

CONFIG = Path("purrfessor.toml")
EXAMPLE = PKG / "templates" / "purrfessor.example.toml"


def ask(prompt: str, default: str = "") -> str:
    got = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
    return got or default


def gh(*args: str, stdin: str | None = None, check: bool = True) -> str:
    r = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"gh {' '.join(args[:3])} failed: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


def gh_ok(*args: str) -> bool:
    return subprocess.run(["gh", *args], capture_output=True, text=True).returncode == 0


def canvas_whoami(base: str, token: str) -> str | None:
    req = urllib.request.Request(f"{base.rstrip('/')}/api/v1/users/self", headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r).get("name")
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None


def set_secret(repo: str, name: str, value: str) -> None:
    gh("secret", "set", name, "-R", repo, stdin=value)
    print(f"  ✓ secret {name}")


def init() -> None:
    if not shutil.which("gh"):
        raise SystemExit("Please install the GitHub CLI (https://cli.github.com) and run `gh auth login` first.\n"
                         "请先安装 GitHub CLI 并登录（gh auth login）。")
    repo = gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner", check=False)
    if not repo:
        raise SystemExit("Run this inside your copy of the Purrfessor template (a GitHub repo).\n"
                         "请在你用模板创建的 GitHub 仓库目录里运行。")
    print(f"🧙🐱 Purrfessor · 喵教授 — setting up {repo}\n")

    names = presets()
    print("School presets / 学校预设: " + ", ".join(names) + "  (generic = any Canvas school / 其他 Canvas 学校)")
    preset = ask("Preset / 预设", "ucr" if "ucr" in names else "generic")
    school = {}
    if preset == "generic":
        school = {"name": ask("School name / 学校名称", "My School"),
                  "canvas_url": ask("Canvas URL (e.g. https://canvas.myschool.edu)"),
                  "timezone": ask("Time zone / 时区", "America/New_York")}
    language = ask("Language / 语言 (zh = 中文, en = English)", "zh").lower()
    language = language if language in ("zh", "en") else "en"
    name = ask("Your name on the page / 页面上显示的名字", "Me")

    base = school.get("canvas_url") or _preset_canvas(preset)
    while True:
        token = getpass.getpass("Canvas token (Account → Settings → New Access Token; hidden / 不显示): ").strip()
        who = canvas_whoami(base, token)
        if who:
            print(f"  ✓ Canvas: {who}")
            break
        print("  ✗ That token doesn't work with this Canvas. Try again. / token 不可用，请重试。")
    while True:
        pw = getpass.getpass("Site password / 网站口令 (hidden / 不显示): ")
        if pw and pw == getpass.getpass("Again / 再输一次: "):
            break
        print("  ✗ Didn't match. / 两次不一致。")
    gemini = getpass.getpass("Gemini API key (optional, Enter to skip / 可选，回车跳过; hidden): ").strip()

    text = EXAMPLE.read_text(encoding="utf-8")
    text = (text.replace('preset = "ucr"', f'preset = "{preset}"').replace('language = "zh"', f'language = "{language}"')
                .replace('name = "Alex"', f'name = "{name}"'))
    if school:
        text += "\n[school]\n" + "".join(f'{k} = "{v}"\n' for k, v in school.items())
    if not CONFIG.exists() or ask(f"{CONFIG} exists — overwrite? / 已存在，覆盖？ (y/N)", "n").lower() == "y":
        CONFIG.write_text(text, encoding="utf-8")
        print(f"  ✓ wrote {CONFIG} (private — git-ignored / 私密，不进仓库)")

    set_secret(repo, "CANVAS_TOKEN", token)
    set_secret(repo, "SITE_PASSWORD", pw)
    if gemini:
        set_secret(repo, "GEMINI_API_KEY", gemini)
    set_secret(repo, "PURRFESSOR_CONFIG", CONFIG.read_text(encoding="utf-8"))
    gh("variable", "set", "PURRFESSOR_ENABLED", "-R", repo, "--body", "true")
    print("  ✓ variable PURRFESSOR_ENABLED=true")
    pages = f"repos/{repo}/pages"
    if gh("api", pages, "--jq", ".build_type", check=False) == "workflow" or \
            gh_ok("api", "-X", "POST", pages, "-f", "build_type=workflow") or \
            gh_ok("api", "-X", "PUT", pages, "-f", "build_type=workflow"):
        print("  ✓ GitHub Pages → GitHub Actions")
    else:
        print(f"  ! Please enable Pages by hand: https://github.com/{repo}/settings/pages → Source: GitHub Actions\n"
              "    请手动开启：Settings → Pages → Source 选 GitHub Actions")

    gh("workflow", "run", "deploy.yml", "-R", repo, check=False)
    print("  ✓ first deploy started (takes ~3 min) / 已触发第一次部署（约 3 分钟）")
    if preset == "generic":
        print("\n  ! Set [term] week1_monday / last_class_day and your [[classes]] in purrfessor.toml,\n"
              "    then run `purrfessor config-upload`. / 请在 purrfessor.toml 里填写学期日期和课表，再运行 config-upload。")
    owner, _, rest = repo.partition("/")
    print(f"\nYour page / 你的页面: https://{owner.lower()}.github.io/{rest}/  🎉")


def _preset_canvas(preset: str) -> str:
    import tomllib
    with open(PKG / "presets" / f"{preset}.toml", "rb") as f:
        return tomllib.load(f).get("school", {}).get("canvas_url", "")


def config_upload() -> None:
    repo = gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner")
    set_secret(repo, "PURRFESSOR_CONFIG", CONFIG.read_text(encoding="utf-8"))
    gh("workflow", "run", "deploy.yml", "-R", repo)
    print("  ✓ redeploy started / 已触发重新部署")


def lock_args(argv: list[str]) -> None:
    """One Staticrypt argument per line, for `mapfile -t ARGS < <(purrfessor lock-args)` in the workflow."""
    from .config import load
    from .i18n import T
    path = argv[argv.index("--config") + 1] if "--config" in argv else CONFIG
    S = load(path)
    t = T(S.language)
    for flag, key in [("--template-title", "lock_title"), ("--template-instructions", "lock_instructions"),
                      ("--template-button", "lock_button"), ("--template-placeholder", "lock_placeholder"),
                      ("--template-remember", "lock_remember"), ("--template-error", "lock_error")]:
        print(flag)
        print(t(key, name=S.name))
    print("--template-color-primary")
    print("#2f6fd6")


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    cmd, rest = (argv[0], argv[1:]) if argv else ("help", [])
    if cmd == "init":
        init()
    elif cmd == "build":
        from .build import main as build
        build(rest)
    elif cmd == "config-upload":
        config_upload()
    elif cmd == "lock-args":
        lock_args(rest)
    elif cmd == "snapshot":
        from .snapshot import cli as snapshot
        snapshot(rest)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()

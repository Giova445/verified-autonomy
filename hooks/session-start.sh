#!/usr/bin/env bash
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
read -r -d '' SOURCE <<'PY'
import glob
import json
import os
import re
import sys

sys.path.insert(0, sys.argv[1])
from state import CONFIG_REL, clean_id, load_json, project_root, read_input

HINT = ("verified-autonomy is installed but not armed in this repo. When the user asks for work to be "
        "done autonomously or verified, or asks to set it up, run the verified-autonomy:setup skill first.")
UNATTENDED = ("<unattended>Nobody is watching this run. Do not end a turn with a summary that names the "
              "next step, an offer to continue, or a list of decisions none of which blocks the rest; put "
              "status in the same message as your next tool call, and end a turn only when nothing can "
              "move without a person.</unattended>")


def version_key(text):
    return tuple(int(x) for x in re.findall(r"\d+", text or ""))


def plugin_version(path):
    data = load_json(path)
    return data.get("version") if isinstance(data, dict) else None


def versions_in(config_dir):
    plugins = os.path.join(config_dir, "plugins")
    paths = [os.path.join(plugins, "marketplaces", "verified-autonomy", ".claude-plugin", "plugin.json")]
    paths += glob.glob(os.path.join(plugins, "cache", "verified-autonomy", "verified-autonomy",
                                    "*", ".claude-plugin", "plugin.json"))
    return [v for v in map(plugin_version, paths) if v]


def stale_warning(plugin_root):
    running = plugin_version(os.path.join(plugin_root, ".claude-plugin", "plugin.json"))
    if not running:
        return ""
    home = os.path.expanduser("~")
    dirs = {os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home, ".claude")}
    dirs |= {d for d in glob.glob(os.path.join(home, ".claude*")) if os.path.isdir(d)}
    newest = max((v for d in dirs for v in versions_in(d)), key=version_key, default=None)
    if newest and version_key(newest) > version_key(running):
        return ("verified-autonomy %s is running, but %s is already on this machine. Run /plugin "
                "marketplace update verified-autonomy, then /plugin update "
                "verified-autonomy@verified-autonomy, then restart." % (running, newest))
    return ""


def in_git_repo(root):
    path = os.path.abspath(root)
    while not os.path.exists(os.path.join(path, ".git")):
        parent = os.path.dirname(path)
        if parent == path:
            return False
        path = parent
    return True


def runner_command(root, plugin_root):
    if os.access(os.path.join(root, "bin", "verify"), os.X_OK):
        return "./bin/verify done"
    return '"%s" done' % os.path.join(plugin_root, "bin", "verify")


def context_for(root, plugin_root, source):
    if not in_git_repo(root):
        return ""
    if not os.path.isfile(os.path.join(root, CONFIG_REL)):
        return HINT if source in ("", "startup") else ""
    text = ("verified-autonomy is armed here: %s must exit 0 before you claim the work is done.\n"
            "The Stop hook runs it for you and names what is still open." % runner_command(root, plugin_root))
    return text + "\n" + UNATTENDED if os.environ.get("VERIFIED_AUTONOMY_UNATTENDED") == "1" else text


data = read_input()
source = clean_id(data.get("source"), 32)
root = project_root(data)
plugin_root = os.path.dirname(sys.argv[1])
out = {}
context = context_for(root, plugin_root, source)
if context:
    out["hookSpecificOutput"] = {"hookEventName": "SessionStart", "additionalContext": context}
warning = stale_warning(plugin_root) if source in ("", "startup", "resume") else ""
if warning:
    out["systemMessage"] = warning
if out:
    print(json.dumps(out))
PY
exec python3 -c "$SOURCE" "$HERE"

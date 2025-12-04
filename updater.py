import json
import os
import sys
import tempfile
import zipfile
import shutil
import subprocess

import requests

INSTALL_ROOT = os.path.dirname(os.path.abspath(sys.argv[0]))
CONFIG_PATH = os.path.join(INSTALL_ROOT, "data.json")


def load_config():
    defaults = {
        "show_update_message": True,
        "update_message_title": "Updating to the latest version",
        "update_message_body": "A new version of the application is available: {version}",
    }
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user_config = json.load(f)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Configuration file not found: {CONFIG_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Configuration file is invalid JSON: {exc}") from exc

    config = {**defaults, **user_config}

    required_keys = [
        "owner",
        "repo",
        "asset_name",
        "main_exe_name",
        "state_filename",
        "versions_dir_name",
        "version_dir_prefix",
    ]
    missing = [key for key in required_keys if not config.get(key)]
    if missing:
        raise RuntimeError(
            f"Missing configuration values in data.json: {', '.join(missing)}"
        )

    return config


CONFIG = load_config()

OWNER = CONFIG["owner"]
REPO = CONFIG["repo"]
ASSET_NAME = CONFIG["asset_name"]
MAIN_EXE_NAME = CONFIG["main_exe_name"]
VERSION_DIR_PREFIX = CONFIG["version_dir_prefix"]
VERSIONS_DIR_NAME = CONFIG["versions_dir_name"]
SHOW_UPDATE_MESSAGE = bool(CONFIG.get("show_update_message"))
UPDATE_MESSAGE_TITLE = CONFIG.get("update_message_title", "")
UPDATE_MESSAGE_BODY = CONFIG.get("update_message_body", "")

API_LATEST_URL = f"https://api.github.com/repos/{OWNER}/{REPO}/releases/latest"
STATE_FILE = os.path.join(INSTALL_ROOT, CONFIG["state_filename"])
VERSIONS_DIR = os.path.join(INSTALL_ROOT, VERSIONS_DIR_NAME)


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"version": None, "path": None}


def save_state(version, path):
    data = {"version": version, "path": path}
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)


def ensure_versions_dir():
    os.makedirs(VERSIONS_DIR, exist_ok=True)


def normalize_state_install_path(state):
    """Move legacy installs into the versions folder so cleanup logic works."""
    path = state.get("path")
    if not path:
        return state

    rel_path = os.path.normpath(path)
    if os.path.isabs(rel_path):
        rel_path = os.path.relpath(rel_path, INSTALL_ROOT)

    if rel_path.startswith(VERSIONS_DIR_NAME + os.sep) or rel_path == VERSIONS_DIR_NAME:
        state["path"] = rel_path
        return state

    current_abs = os.path.join(INSTALL_ROOT, rel_path)
    if not os.path.isdir(current_abs):
        return state

    ensure_versions_dir()
    dest_rel = os.path.join(VERSIONS_DIR_NAME, os.path.basename(rel_path))
    dest_abs = os.path.join(INSTALL_ROOT, dest_rel)

    if os.path.normcase(current_abs) == os.path.normcase(dest_abs):
        state["path"] = dest_rel
        save_state(state.get("version"), dest_rel)
        return state

    if os.path.isdir(dest_abs):
        shutil.rmtree(dest_abs)

    shutil.move(current_abs, dest_abs)
    state["path"] = dest_rel
    save_state(state.get("version"), dest_rel)
    return state


def cleanup_old_versions(preserve_paths):
    """Remove version directories outside the preserve list."""
    preserve_abs = set()
    for rel in preserve_paths:
        if not rel:
            continue
        abs_path = os.path.join(INSTALL_ROOT, rel)
        preserve_abs.add(os.path.normcase(os.path.normpath(abs_path)))

    candidates = []

    if os.path.isdir(VERSIONS_DIR):
        for entry in os.listdir(VERSIONS_DIR):
            candidate = os.path.join(VERSIONS_DIR, entry)
            if os.path.isdir(candidate):
                candidates.append(candidate)

    for entry in os.listdir(INSTALL_ROOT):
        if not entry.startswith(VERSION_DIR_PREFIX):
            continue
        candidate = os.path.join(INSTALL_ROOT, entry)
        if os.path.isdir(candidate):
            candidates.append(candidate)

    for candidate in candidates:
        if os.path.normcase(os.path.normpath(candidate)) in preserve_abs:
            continue
        shutil.rmtree(candidate, ignore_errors=True)


def get_latest_release(token=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    r = requests.get(API_LATEST_URL, headers=headers, timeout=10)
    r.raise_for_status()
    data = r.json()

    tag = data["tag_name"]
    assets = data.get("assets", [])
    asset = None
    for a in assets:
        if a.get("name") == ASSET_NAME:
            asset = a
            break
    if not asset:
        raise RuntimeError(f"Asset {ASSET_NAME} not found in latest release")

    download_url = asset["browser_download_url"]
    return tag, download_url


def download_zip(url, dest_path, token=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with requests.get(url, headers=headers, stream=True, timeout=30) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)


def extract_zip(zip_path, target_dir):
    # Remove any existing contents for this version
    if os.path.isdir(target_dir):
        shutil.rmtree(target_dir)
    os.makedirs(target_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target_dir)


def ensure_latest_installed():
    # Optional: read token from env if you need private repos
    token = os.getenv("GITHUB_TOKEN")

    ensure_versions_dir()

    state = normalize_state_install_path(load_state())
    installed_version = state.get("version")
    current_path = state.get("path")

    latest_version, download_url = get_latest_release(token=token)

    # Simple string compare; you can also use packaging.version if you need smarter semantics
    if installed_version == latest_version:
        # Already up to date
        if current_path and os.path.isdir(os.path.join(INSTALL_ROOT, current_path)):
            return current_path, latest_version

    if SHOW_UPDATE_MESSAGE:
        import threading
        import tkinter as tk
        from tkinter import messagebox

        def show_message():
            root = tk.Tk()
            root.withdraw()
            root.update()
            messagebox.showinfo(
                UPDATE_MESSAGE_TITLE,
                UPDATE_MESSAGE_BODY.format(version=latest_version),
            )
            root.destroy()

        threading.Thread(target=show_message, daemon=True).start()

    # Need to download and install new version
    version_dir_name = f"{VERSION_DIR_PREFIX}{latest_version}"
    relative_dir = os.path.join(VERSIONS_DIR_NAME, version_dir_name)
    target_dir = os.path.join(INSTALL_ROOT, relative_dir)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_zip_path = os.path.join(tmp_dir, "app.zip")
        download_zip(download_url, tmp_zip_path, token=token)
        extract_zip(tmp_zip_path, target_dir)

    # Save state pointing to the new version
    save_state(latest_version, relative_dir)

    cleanup_old_versions({current_path, relative_dir})
    return relative_dir, latest_version


def launch_current():
    state = load_state()
    version_dir_name = state.get("path")
    if not version_dir_name:
        raise RuntimeError("No installed version found in state.json")

    app_dir = os.path.join(INSTALL_ROOT, version_dir_name)
    exe_path = os.path.join(app_dir, MAIN_EXE_NAME)
    if not os.path.isfile(exe_path):
        raise RuntimeError(f"Main executable not found: {exe_path}")

    # Start the app and exit launcher
    subprocess.Popen([exe_path], cwd=app_dir)
    # Let the launcher exit
    sys.exit(0)


def main():
    try:
        _, _ = ensure_latest_installed()
    except Exception as e:
        # If update fails, optionally fall back to existing version if any
        # You might want to log this to a file.
        print(f"Update check failed: {e}", file=sys.stderr)

    launch_current()


if __name__ == "__main__":
    main()

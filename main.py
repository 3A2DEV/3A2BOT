# Copyright (c) 2025, Marco Noce <nce.marco@gmail.com>
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import re
import json
import time
import io
import zipfile
import requests
from threading import Thread
from flask import Flask
from github import Github

app = Flask(__name__)

@app.route("/")
def home():
    return "3A2DEV Bot is alive!", 200

# === Config ===
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO_NAME = "3A2DEV/a2dev.general"
PROCESSED_FILE = "processed.json"

g = Github(GITHUB_TOKEN)
repo = g.get_repo(REPO_NAME)

# Load previously processed PRs
processed = set()
if os.path.exists(PROCESSED_FILE):
    try:
        with open(PROCESSED_FILE) as f:
            data = f.read().strip()
            if data:
                processed = set(json.loads(data))
    except Exception as e:
        print(f"⚠️ Failed to load processed.json: {e}")

# === Error Patterns ===
error_markers = [
    "FAILED", "failed", "ERROR", "Traceback", "SyntaxError",
    "ImportError", "ModuleNotFoundError", "assert",
    "ERROR! ", "fatal:", "task failed", "collection failure",
    "Test failures:", "ansible-test sanity", "invalid-documentation-markup",
    "The test 'ansible-test sanity", "sanity failure", "test failed"
]

# === Bot Logic ===
def parse_component_name(body):
    match = re.search(r"###\s*Component Name\s*\n+([a-zA-Z0-9_]+)", body)
    return match.group(1) if match else None

def file_exists(path):
    try:
        repo.get_contents(path)
        return True
    except:
        return False

def comment_with_link(issue, path):
    url = f"https://github.com/{REPO_NAME}/blob/main/{path}"
    body = f"""Files identified in the description:

- [**{path}**]({url})"""
    issue.create_comment(body)
    print(f"✅ Commented on #{issue.number} with module path")

def add_label(item, label):
    labels = [l.name for l in item.labels]
    if label not in labels:
        try:
            item.add_to_labels(label)
            print(f"🏷️ Added label '{label}' to #{item.number}")
        except Exception as e:
            print(f"❌ Failed to add label '{label}' to #{item.number}: {e}")

def remove_label(item, label):
    labels = [l.name for l in item.labels]
    if label in labels:
        try:
            item.remove_from_labels(label)
            print(f"❌ Removed label '{label}' from #{item.number}")
        except Exception as e:
            print(f"⚠️ Failed to remove label '{label}' from #{item.number}: {e}")

def check_ci_errors_and_comment(pr):
    print(f"🔎 Checking CI logs for PR #{pr.number}...")
    runs = repo.get_workflow_runs(event="pull_request", head_sha=pr.head.sha)
    if runs.totalCount == 0:
        print("❌ No CI runs found.")
        return

    latest_run = runs[0]
    if latest_run.status != "completed":
        print("⏳ CI is still running...")
        return

    logs_url = latest_run.logs_url
    print(f"📦 Downloading logs from: {logs_url}")
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(logs_url, headers=headers)
    if r.status_code != 200:
        print("⚠️ Failed to download logs")
        return

    errors_found = []
    with zipfile.ZipFile(io.BytesIO(r.content)) as zip_file:
        for file_name in zip_file.namelist():
            if not file_name.endswith(".txt"):
                continue
            with zip_file.open(file_name) as f:
                content = f.read().decode("utf-8", errors="ignore").lower()
                for marker in error_markers:
                    if marker.lower() in content:
                        print(f"❌ Found '{marker}' in {file_name}")
                        snippet = "\n".join(content.splitlines()[:50])
                        errors_found.append((file_name, snippet))
                        break

    if not errors_found:
        print(f"✅ No CI errors for PR #{pr.number}.")
        add_label(pr, "success")
        remove_label(pr, "stale_ci")
        remove_label(pr, "needs_revision")
        return

    # Compose error comment
    comment_body = "🚨 **CI Test Failures Detected**\n\n"
    for file_name, snippet in errors_found:
        comment_body += f"**{file_name}**\n```text\n{snippet[:1000]}\n```\n\n"

    existing_comments = pr.get_issue_comments()
    if not any("CI Test Failures Detected" in c.body for c in existing_comments):
        pr.create_issue_comment(comment_body)
        print(f"💬 Posted CI failure comment on PR #{pr.number}")
    else:
        print("💬 CI error comment already exists.")

    add_label(pr, "stale_ci")
    add_label(pr, "needs_revision")
    remove_label(pr, "success")

def get_unprocessed_items():
    issues = repo.get_issues(state="open", sort="created", direction="desc")
    items = []
    for i in issues:
        labels = [l.name for l in i.labels]
        if (
            i.number not in processed
            or any(label in labels for label in ["success", "stale_ci", "needs_revision"])
        ):
            items.append(i)
    return items

def bot_loop():
    global processed
    print("🤖 Bot loop started...")
    while True:
        for item in get_unprocessed_items():
            print(f"🔄 Processing #{item.number}...")
            body = item.body or ""
            component = parse_component_name(body)
            if component:
                file_path = f"plugins/modules/{component}.py"
                if file_exists(file_path):
                    comment_with_link(item, file_path)

            if item.pull_request:
                pr = repo.get_pull(item.number)
                check_ci_errors_and_comment(pr)

            processed.add(item.number)

        with open(PROCESSED_FILE, "w") as f:
            json.dump(list(processed), f)

        print("⏳ Sleeping for 5 minutes...")
        time.sleep(300)

# === Start Everything ===
def start_bot():
    Thread(target=bot_loop).start()

start_bot()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

# Copyright (c) 2025, Marco Noce <nce.marco@gmail.com>
# GNU General Public License v3.0+
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

# === Load processed PRs ===
processed = set()
if os.path.exists(PROCESSED_FILE):
    try:
        with open(PROCESSED_FILE) as f:
            data = f.read().strip()
            if data:
                processed = set(json.loads(data))
    except Exception as e:
        print(f"⚠️ Failed to load processed.json: {e}")

# === Error Markers ===
error_markers = [
    "FAILED", "failed", "ERROR", "Traceback", "SyntaxError",
    "ImportError", "ModuleNotFoundError", "assert",
    "ERROR! ", "fatal:", "task failed", "collection failure",
    "Test failures:", "ansible-test sanity", "invalid-documentation-markup",
    "non-existing option", "The test 'ansible-test sanity", "sanity failure",
    "test failed", "invalid value"
]

# === Utilities ===
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

# === CI Analysis ===
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
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    r = requests.get(logs_url, headers=headers)
    if r.status_code != 200:
        print("⚠️ Failed to download logs")
        return

    # === Get real job names via GitHub REST API ===
    job_lookup = {}
    jobs_url = f"https://api.github.com/repos/{REPO_NAME}/actions/runs/{latest_run.id}/jobs"
    jr = requests.get(jobs_url, headers=headers)
    if jr.status_code == 200:
        for job in jr.json().get("jobs", []):
            key = re.sub(r"[^a-z0-9]", "_", job["name"].lower())
            job_lookup[key] = job["name"]
    else:
        print("⚠️ Failed to get job names from GitHub API")

    # === Scan log files grouped by job folder ===
    job_logs = {}
    scanned_logs = 0

    with zipfile.ZipFile(io.BytesIO(r.content)) as zip_file:
        folders = {}

        # Group files by job folder
        for file_name in zip_file.namelist():
            if not file_name.endswith(".txt"):
                continue
            folder = file_name.split("/")[0]
            folders.setdefault(folder, []).append(file_name)

        for folder, files in folders.items():
            scanned_logs += 1
            normalized = re.sub(r"^\d+_", "", folder.lower())
            normalized = re.sub(r"[^a-z0-9]", "_", normalized)

            # Fuzzy match to job name
            job_name = None
            for key, name in job_lookup.items():
                if key.startswith(normalized) or normalized in key:
                    job_name = name
                    break
            if not job_name:
                job_name = re.sub(r"^\d+_", "", folder).replace("_", " ")

            print(f"🔍 Scanning job folder: {folder} → {job_name}")

            for file_name in files:
                with zip_file.open(file_name) as f:
                    content = f.read().decode("utf-8", errors="ignore")
                    lines = content.splitlines()
                    for i, line in enumerate(lines):
                        normalized_line = line.strip().lower()
                        if any(marker.lower() in normalized_line for marker in error_markers):
                            print(f"❌ Error in job '{job_name}' from file '{file_name}'")
                            start = max(0, i - 5)
                            end = min(len(lines), i + 10)
                            snippet = "\n".join(lines[start:end])
                            job_logs.setdefault(job_name, []).append(snippet)
                            break

    errors_by_job = {k: v for k, v in job_logs.items() if v}

    if scanned_logs == 0:
        print("⚠️ No logs were scanned at all.")
        return

    if not errors_by_job:
        print(f"✅ No CI errors found for PR #{pr.number}.")
        existing_comments = list(pr.get_issue_comments())
        bot_comments = [c for c in existing_comments if "CI Test Failures Detected" in c.body]
        latest_comment = bot_comments[-1] if bot_comments else None

        if latest_comment and "<details>" not in latest_comment.body:
            archived_body = f"""<details>
<summary>🕙 Outdated CI result (auto-archived by bot)</summary>

{latest_comment.body}
</details>"""
            latest_comment.edit(archived_body)
            print(f"📦 Archived old CI comment on PR #{pr.number}")

        add_label(pr, "success")
        remove_label(pr, "stale_ci")
        remove_label(pr, "needs_revision")
        return

    # === Build comment body ===
    comment_body = "🚨 **CI Test Failures Detected**\n\n"
    for job_name, snippets in errors_by_job.items():
        comment_body += f"### 🔧 {job_name}\n"
        for snippet in snippets:
            comment_body += f"```text\n{snippet[:1000]}\n```\n\n"

    # === Check for previous bot comment ===
    existing_comments = list(pr.get_issue_comments())
    bot_comments = [c for c in existing_comments if "CI Test Failures Detected" in c.body]
    latest_comment = bot_comments[-1] if bot_comments else None

    if latest_comment and comment_body.strip() in latest_comment.body:
        print("🔁 CI errors unchanged — skipping comment.")
        return

    if latest_comment and "<details>" not in latest_comment.body:
        archived_body = f"""<details>
<summary>🕙 Outdated CI result (auto-archived by bot)</summary>

{latest_comment.body}
</details>"""
        latest_comment.edit(archived_body)
        print(f"📦 Archived old CI comment on PR #{pr.number}")

    pr.create_issue_comment(comment_body)
    print(f"💬 Posted new CI failure comment on PR #{pr.number}")

    add_label(pr, "stale_ci")
    add_label(pr, "needs_revision")
    remove_label(pr, "success")

# === PR Detection ===
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

# === Bot Loop ===
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

        print("⏳ Sleeping for 3 minutes...")
        time.sleep(180)

# === Start Bot ===
def start_bot():
    Thread(target=bot_loop).start()

start_bot()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

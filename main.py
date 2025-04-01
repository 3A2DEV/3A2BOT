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

# === Configuration ===
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO_NAME = "3A2DEV/a2dev.general"
PROCESSED_FILE = "processed.json"

g = Github(GITHUB_TOKEN)
repo = g.get_repo(REPO_NAME)

processed = set()
if os.path.exists(PROCESSED_FILE):
    try:
        with open(PROCESSED_FILE) as f:
            processed = set(json.load(f))
    except Exception as e:
        print(f"⚠️ Failed to load {PROCESSED_FILE}: {e}")

error_markers = [
    "FAILED", "ERROR", "Traceback", "SyntaxError", "assert", "ImportError",
    "ModuleNotFoundError", "task failed", "Test failures:", "fatal:", "invalid value",
    "sanity failure", "invalid-documentation-markup", "non-existing option",
]

# === Helpers ===
def add_label(pr, label):
    if label not in [l.name for l in pr.labels]:
        pr.add_to_labels(label)

def remove_label(pr, label):
    if label in [l.name for l in pr.labels]:
        pr.remove_from_labels(label)

def archive_old_ci_comment(pr):
    comments = list(pr.get_issue_comments())
    for comment in reversed(comments):
        if "CI Test Failures Detected" in comment.body and "<details>" not in comment.body:
            comment.edit(f"<details>\n<summary>🕙 Outdated CI result</summary>\n\n{comment.body}\n</details>")
            break

def get_latest_workflow_run(pr):
    runs = repo.get_workflow_runs(event="pull_request", head_sha=pr.head.sha)
    return runs[0] if runs.totalCount > 0 else None

def normalize_key(name):
    return re.sub(r"[^a-z0-9]", "_", name.lower())

def extract_errors_from_logs(zip_content, job_lookup):
    job_errors = {}
    seen = set()

    with zipfile.ZipFile(io.BytesIO(zip_content)) as zip_file:
        for file_name in zip_file.namelist():
            if not file_name.endswith(".txt"):
                continue

            base = file_name.split("/")[0]
            name_clean = re.sub(r"^\d+_", "", base)
            normalized = normalize_key(name_clean)

            job_name = next((v for k, v in job_lookup.items() if normalized in k), name_clean)
            if job_name in seen:
                continue
            seen.add(job_name)

            with zip_file.open(file_name) as f:
                content = f.read().decode(errors="ignore")
                lines = content.splitlines()
                for i, line in enumerate(lines):
                    if any(m.lower() in line.lower() for m in error_markers):
                        snippet = "\n".join(lines[max(0, i-5):min(len(lines), i+10)])
                        job_errors[job_name] = snippet[:1000]
                        break

    return job_errors

def check_ci_errors_and_comment(pr):
    print(f"🔎 Analyzing CI logs for PR #{pr.number}")
    run = get_latest_workflow_run(pr)
    if not run or run.status != "completed":
        print("⏳ No completed workflow run found.")
        return

    # Fetch logs
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    log_resp = requests.get(run.logs_url, headers=headers)
    if log_resp.status_code != 200:
        print("❌ Failed to fetch logs.")
        return

    # Get job names from API
    jobs_resp = requests.get(
        f"https://api.github.com/repos/{REPO_NAME}/actions/runs/{run.id}/jobs",
        headers=headers
    )
    job_lookup = {
        normalize_key(job["name"]): job["name"]
        for job in jobs_resp.json().get("jobs", []) if "name" in job
    }

    errors = extract_errors_from_logs(log_resp.content, job_lookup)

    if not errors:
        print("✅ No CI errors found.")
        archive_old_ci_comment(pr)
        add_label(pr, "success")
        remove_label(pr, "stale_ci")
        remove_label(pr, "needs_revision")
        return

    # Create error comment
    comment = "🚨 **CI Test Failures Detected**\n\n"
    for job, snippet in errors.items():
        comment += f"### 🔧 {job}\n```text\n{snippet}\n```\n\n"

    comments = list(pr.get_issue_comments())
    for c in reversed(comments):
        if "CI Test Failures Detected" in c.body:
            if comment.strip() in c.body:
                print("🔁 Same errors already posted.")
                return
            archive_old_ci_comment(pr)
            break

    pr.create_issue_comment(comment)
    print("💬 Posted CI failure comment.")

    add_label(pr, "stale_ci")
    add_label(pr, "needs_revision")
    remove_label(pr, "success")

# === Component Link Helper ===
def post_component_link(issue):
    match = re.search(r"###\s*Component Name\s*\n+([a-zA-Z0-9_]+)", issue.body or "")
    if match:
        comp = match.group(1)
        path = f"plugins/modules/{comp}.py"
        try:
            repo.get_contents(path)
            issue.create_comment(f"Files identified in the description:\n\n- [**{path}**](https://github.com/{REPO_NAME}/blob/main/{path})")
        except:
            pass

# === Main Bot Loop ===
def get_targets():
    return [
        i for i in repo.get_issues(state="open")
        if i.number not in processed or any(l.name in ["success", "needs_revision", "stale_ci"] for l in i.labels)
    ]

def bot_loop():
    global processed
    print("🤖 Bot loop started")
    while True:
        for item in get_targets():
            print(f"🔄 Processing #{item.number}")
            post_component_link(item)
            if item.pull_request:
                pr = repo.get_pull(item.number)
                check_ci_errors_and_comment(pr)
            processed.add(item.number)

        with open(PROCESSED_FILE, "w") as f:
            json.dump(list(processed), f)

        print("⏳ Sleeping 3 min...")
        time.sleep(180)

# === Launch Bot ===
def start_bot():
    Thread(target=bot_loop).start()

start_bot()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

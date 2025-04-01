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

# Configuration and constants
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO_NAME = "3A2DEV/a2dev.general"
PROCESSED_FILE = "processed.json"

# Initialize GitHub repository
g = Github(GITHUB_TOKEN)
repo = g.get_repo(REPO_NAME)

# Load processed issue/PR numbers
processed = set()
if os.path.exists(PROCESSED_FILE):
    try:
        with open(PROCESSED_FILE) as f:
            processed = set(json.load(f))
    except Exception as e:
        print(f"⚠️ Failed to load {PROCESSED_FILE}: {e}")

# Error markers for identifying failures in logs
error_markers = [
    "failed", "error", "traceback", "syntaxerror",
    "importerror", "modulenotfounderror", "assert",
    "error! ", "fatal:", "task failed", "collection failure",
    "test failures:", "ansible-test sanity", "invalid-documentation-markup",
    "non-existing option", "sanity failure", "test failed", "invalid value"
]

# Patterns to skip irrelevant lines
skip_patterns = re.compile(
    r"coverage:|##\[group\]|shell:|Cleaning up orphan processes|core-github-repository-slug|pull-request-change-detection",
    re.IGNORECASE
)

def extract_error_snippet(lines):
    """
    Extracts a snippet from the log around lines that start with "FAILED" or "FATAL".
    This approach focuses on generic error patterns.
    """
    candidates = []
    for i, line in enumerate(lines):
        if re.match(r'^(FAILED|FATAL)', line.strip()):
            # Capture a snippet: 3 lines before and 7 lines after the error line
            snippet = "\n".join(lines[max(0, i-3):min(len(lines), i+7)])
            candidates.append((i, snippet))
    
    if candidates:
        # Optionally, choose the last candidate if multiple errors occur
        return candidates[-1][1]
    return None

def archive_old_comment(pr):
    """
    Archive the old bot comment by wrapping it in a collapsible <details> tag.
    """
    comments = list(pr.get_issue_comments())
    bot_comments = [c for c in comments if "CI Test Failures Detected" in c.body]
    if bot_comments:
        latest = bot_comments[-1]
        if "<details>" not in latest.body:
            archived = f"""<details>
<summary>🕙 Outdated CI result (auto-archived by bot)</summary>

{latest.body}
</details>"""
            latest.edit(archived)
            print("📦 Archived old CI comment")

def post_or_update_comment(pr, new_body):
    """
    Post a new comment or update the existing one if the content has changed.
    """
    existing = list(pr.get_issue_comments())
    bot_comments = [c for c in existing if "CI Test Failures Detected" in c.body]
    if bot_comments:
        last = bot_comments[-1]
        if new_body.strip() != last.body.strip():
            archive_old_comment(pr)
            pr.create_issue_comment(new_body)
            print("💬 Posted updated CI failures")
        else:
            print("🔁 Same error content. Skipping comment.")
    else:
        pr.create_issue_comment(new_body)
        print("💬 Posted first CI failure comment")

def match_job_for_log(normalized_folder, job_lookup):
    """
    Attempt to match the normalized folder name from the log file with a job from job_lookup.
    The match is bidirectional: it checks if one string is contained in the other.
    """
    for key, job in job_lookup.items():
        if normalized_folder in key or key in normalized_folder:
            return job
    return None

def check_ci_errors_and_comment(pr):
    """
    Check CI workflow logs for the given pull request, extract error snippets for failed jobs,
    update labels based on test results, and update or post a comment on the PR with the relevant error details.
    """
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
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    r = requests.get(logs_url, headers=headers)
    if r.status_code != 200:
        print("⚠️ Failed to download logs")
        return

    # Build a lookup for failed jobs using a normalized key
    job_lookup = {}
    failed_jobs = set()
    jobs_url = f"https://api.github.com/repos/{REPO_NAME}/actions/runs/{latest_run.id}/jobs"
    jr = requests.get(jobs_url, headers=headers)
    if jr.status_code == 200:
        for job in jr.json().get("jobs", []):
            name = job["name"]
            if job["conclusion"] == "failure":
                key = re.sub(r"[^a-z0-9]", "_", name.lower())
                job_lookup[key] = name
                failed_jobs.add(name)
    else:
        print("⚠️ Failed to fetch job list")
        return

    # Update labels based on the overall test result
    if not failed_jobs:
        print(f"✅ All jobs passed for PR #{pr.number}.")
        archive_old_comment(pr)
        # Remove failure-related labels and add success label
        remove_label(pr, "needs_revision")
        remove_label(pr, "stale_ci")
        add_label(pr, "success")
        return

    # There are failed jobs; proceed to extract error snippets
    job_logs = {}
    with zipfile.ZipFile(io.BytesIO(r.content)) as zip_file:
        for file_name in zip_file.namelist():
            if not file_name.endswith(".txt"):
                continue

            # Determine folder name from the file path
            folder = file_name.split("/")[0]
            # Normalize folder name by removing any leading numbers and non-alphanumerics
            normalized_folder = re.sub(r"^\d+_", "", folder).replace(".txt", "").strip().lower()
            normalized_folder = re.sub(r"[^a-z0-9]", "_", normalized_folder)
            
            # Debug: print the normalized folder and job keys
            # print(f"Debug: normalized_folder='{normalized_folder}', job keys: {list(job_lookup.keys())}")

            matched_job = match_job_for_log(normalized_folder, job_lookup)
            if not matched_job or matched_job in job_logs:
                continue

            with zip_file.open(file_name) as f:
                try:
                    content = f.read().decode("utf-8", errors="ignore")
                except Exception as ex:
                    print(f"⚠️ Error reading {file_name}: {ex}")
                    continue
                lines = content.splitlines()
                snippet = extract_error_snippet(lines)
                if snippet:
                    job_logs[matched_job] = snippet

    if not job_logs:
        print("❌ Some jobs failed, but no valid error snippets found.")
        return

    # Build the PR comment body with error details for each failed job
    comment_body = "🚨 **CI Test Failures Detected**\n\n"
    for job, snippet in job_logs.items():
        comment_body += f"### ⚙️ {job}\n"
        comment_body += f"```text\n{snippet[:1000]}\n```\n\n"

    post_or_update_comment(pr, comment_body)
    
    # Update labels for failure: remove success label and add failure label
    remove_label(pr, "success")
    add_label(pr, "stale_ci")
    add_label(pr, "needs_revision")

def parse_component_name(body):
    """
    Parse the component name from the issue/PR body using a header.
    """
    match = re.search(r"###\s*Component Name\s*\n+([a-zA-Z0-9_]+)", body)
    return match.group(1) if match else None

def file_exists(path):
    """
    Check if a given file exists in the repository.
    """
    try:
        repo.get_contents(path)
        return True
    except Exception:
        return False

def comment_with_link(issue, path):
    """
    Comment on the issue/PR with a link to the identified file.
    """
    url = f"https://github.com/{REPO_NAME}/blob/main/{path}"
    body = f"""Files identified in the description:

- [**{path}**]({url})"""
    issue.create_comment(body)
    print(f"✅ Commented on #{issue.number} with module path")

def add_label(item, label):
    if label not in [l.name for l in item.labels]:
        item.add_to_labels(label)
        print(f"🏷️ Added label '{label}' to #{item.number}")

def remove_label(item, label):
    if label in [l.name for l in item.labels]:
        item.remove_from_labels(label)
        print(f"🏷️ Removed label '{label}' from #{item.number}")

def get_unprocessed_items():
    """
    Retrieve all open issues, filtering those that haven't been processed yet
    or have specific labels indicating further review.
    """
    issues = repo.get_issues(state="open", sort="created", direction="desc")
    return [i for i in issues if i.number not in processed or any(l.name in ["success", "stale_ci", "needs_revision"] for l in i.labels)]

def bot_loop():
    """
    Main bot loop: processes unprocessed issues/PRs, checks CI errors,
    updates labels, and updates comments accordingly.
    """
    global processed
    print("🤖 Bot loop started...")
    while True:
        for item in get_unprocessed_items():
            print(f"🔄 Processing #{item.number}...")
            if item.pull_request:
                pr = repo.get_pull(item.number)
                check_ci_errors_and_comment(pr)

            # Optionally comment with a module link if a component is mentioned
            body = item.body or ""
            component = parse_component_name(body)
            if component:
                path = f"plugins/modules/{component}.py"
                if file_exists(path):
                    comment_with_link(item, path)

            processed.add(item.number)

        # Save processed issue/PR numbers
        with open(PROCESSED_FILE, "w") as f:
            json.dump(list(processed), f)

        print("⏳ Sleeping for 3 minutes...")
        time.sleep(180)

def start_bot():
    Thread(target=bot_loop).start()

# Start the bot loop and the web server
start_bot()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

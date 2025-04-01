# Copyright (c) 2025, Marco Noce <nce.marco@gmail.com>
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

def archive_old_comment(pr):
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

def add_label(item, label):
    if label not in [l.name for l in item.labels]:
        item.add_to_labels(label)
        print(f"🏷️ Added label '{label}' to #{item.number}")

def remove_label(item, label):
    if label in [l.name for l in item.labels]:
        item.remove_from_labels(label)
        print(f"🏷️ Removed label '{label}' from #{item.number}")

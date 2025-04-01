# Copyright (c) 2025, Marco Noce <nce.marco@gmail.com>
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

import io
import zipfile
from types import SimpleNamespace

def test_check_ci_errors_and_comment_failed(monkeypatch):
    """
    Test the integrated behavior of check_ci_errors_and_comment when a CI run fails.
    This simulates a workflow run with a logs zip containing an error line.
    """
    # Import the function under test from your ci_checker module.
    from ci_checker import check_ci_errors_and_comment
    import github_client
    import requests
    from config import GITHUB_TOKEN  # In case needed for headers

    # Prepare a dictionary to capture the posted comment.
    captured_comment = {}

    # Dummy function to capture the comment body instead of posting to GitHub.
    def dummy_post_or_update_comment(pr, new_body):
        captured_comment['body'] = new_body

    # Dummy no-op functions for label updates and archiving.
    dummy_add_label = lambda pr, label: None
    dummy_remove_label = lambda pr, label: None
    dummy_archive_comment = lambda pr: None

    # Create a dummy PR object with minimal attributes.
    def dummy_create_issue_comment(body):
        captured_comment['body'] = body

    dummy_pr = SimpleNamespace(
        number=1,
        head=SimpleNamespace(sha="dummy_sha"),
        create_issue_comment=dummy_create_issue_comment,
        get_issue_comments=lambda: []
    )

    # Prepare a dummy workflow run.
    dummy_run = SimpleNamespace(
        status="completed",
        logs_url="https://dummy.url/logs",
        id=123
    )

    # Create a container that mimics the object returned by get_workflow_runs,
    # which has a totalCount attribute and is list-like.
    class DummyRuns:
        def __init__(self, runs):
            self.runs = runs
            self.totalCount = len(runs)
        def __iter__(self):
            return iter(self.runs)
        def __getitem__(self, index):
            return self.runs[index]

    dummy_runs = DummyRuns([dummy_run])

    # Patch the repo's get_workflow_runs to return our DummyRuns container.
    monkeypatch.setattr(
        github_client.repo,
        "get_workflow_runs",
        lambda **kwargs: dummy_runs
    )

    # Create a dummy ZIP archive in memory containing a log file with an error.
    class DummyResponse:
        def __init__(self, content, status_code=200):
            self.content = content
            self.status_code = status_code
        # We'll add a json method here just in case, though it won't be used for logs.
        def json(self):
            return {}

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        dummy_log = (
            "2025-04-01T04:07:58.0000000Z Normal log line\n"
            "2025-04-01T04:07:58.1000000Z \x1b[31mFAILED: Test failed due to assertion\x1b[0m\n"
            "2025-04-01T04:07:58.2000000Z Another normal log line\n"
        )
        # Write the dummy log file using a name that will match the job key.
        # "units (devel).txt" normalizes to "units__devel_", which should match the key
        # created from "Units (devel)".
        zf.writestr("units (devel).txt", dummy_log)
    zip_bytes = zip_buffer.getvalue()

    # Define a custom dummy_requests_get to handle different URLs.
    def dummy_requests_get(url, headers):
        # If the URL is for the jobs endpoint, return a dummy JSON response.
        if "/actions/runs/" in url and "/jobs" in url:
            class DummyJobsResponse:
                status_code = 200
                def json(self):
                    # Return a dummy jobs list with one job marked as failure.
                    return {"jobs": [{"name": "Units (devel)", "conclusion": "failure"}]}
            return DummyJobsResponse()
        else:
            # Otherwise, assume it's the logs URL and return our ZIP archive.
            return DummyResponse(zip_bytes, 200)

    # Patch requests.get with our dummy_requests_get.
    monkeypatch.setattr(requests, "get", dummy_requests_get)

    # Call the function under test with our dummy PR and dummy post/comment functions.
    check_ci_errors_and_comment(
        dummy_pr,
        dummy_add_label,
        dummy_remove_label,
        dummy_post_or_update_comment,
        dummy_archive_comment
    )

    # Verify that the captured comment contains the expected error snippet.
    comment_body = captured_comment.get('body', '')
    assert "FAILED: Test failed due to assertion" in comment_body, \
        f"Expected error snippet not found in comment: {comment_body}"

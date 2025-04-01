# 3A2BOT Collection bot

![collection](https://img.shields.io/badge/ansible-collection%20bot-blue?logo=ansible&logoColor=white) ![Website](https://img.shields.io/website?url=https%3A%2F%2Fthreea2bot.onrender.com&up_message=alive&up_color=green&down_message=down&down_color=red&logo=render&label=3A2BOT%20status) [![Codecov](https://img.shields.io/codecov/c/github/3A2DEV/3A2BOT?logo=codecov)](https://codecov.io/gh/3A2DEV/3A2BOT)


**3A2BOT** is an automated GitHub bot designed to monitor **`a2dev.general`** collection CI workflow runs, extract error details from logs, post comments on pull requests with error snippets, and update PR labels based on test results. It also exposes a simple health-check endpoint using [**Flask**](https://flask.palletsprojects.com/en/stable/).

## Features

- **CI Log Monitoring**:
  
  Automatically retrieves and analyzes CI logs for pull requests.

- **Error Extraction**:

  Extracts error messages from log files (e.g., lines with `FAILED`, `FATAL`, or `ERROR`) after cleaning timestamps and ANSI escape sequences.

- **GitHub Integration**:
  
  Posts comments on PRs with detailed error **snippets** and updates **labels** to reflect CI status (e.g., adding `stale_ci` and `needs_revision` for failures, and `success` for passing tests ).

- **Modular Architecture**:
  
  Code is split across multiple files for maintainability and clarity.

- **Health Check Endpoint**:

  Provides a `JSON` health-check endpoint to verify that the bot is running.

## File Structure

```bash
./
├── main.py              # Entry point: starts the Flask app and bot loop.
├── config.py            # Configuration (GitHub token, repository name, etc.).
├── github_client.py     # Initializes the GitHub client and repository instance.
├── ci_checker.py        # Functions for processing CI logs and extracting error snippets.
├── github_ops.py        # Functions to manage GitHub comments and labels.
├── issue_utils.py       # Utility functions for processing issues and PRs.
├── bot.py               # Main bot loop that ties everything together.
├── conftest.py          # Configuration file for coverage tests.
└── test_bot.py          # Coverage tests file.
```

## Prerequisites

- Python 3.8+
- GitHub Access Token
  
  The bot uses the GitHub API, so you’ll need to create a token with the required permissions and set it in your environment as `GITHUB_TOKEN`

## Deploy

The bot is currently live via **Web Service** on the [**Render**](https://render.com/) platform.

Deploy log example:

```bash
==> Deploying...
==> Running 'python main.py'
🤖 Bot loop started...
 * Serving Flask app 'main'
 * Debug mode: off
WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:10000
Press CTRL+C to quit
==> Your service is live 🎉
==> Detected service running on port 10000
```

## Usage

Start the Bot:

```bash
python main.py
```

Health Check:
```bash
curl http://localhost:10000/
```

## Configuration

- Repository Configuration:
  
  Edit `config.py` to adjust the repository name `REPO_NAME` and processed file `PROCESSED_FILE`.

- Label Management:
  
  The bot uses functions in `github_ops.py` to add or remove labels. Adjust these functions if you need to change how labels are updated.

## License
GNU General Public License v3.0 or later.

See [LICENSE](https://www.gnu.org/licenses/gpl-3.0.txt) to see the full text.
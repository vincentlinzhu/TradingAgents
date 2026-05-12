#!/usr/bin/env python3
"""Headless TradingAgents runner with the rich Live UI.

Same fixed config as run_ticker.py but reuses cli.main.run_analysis() so the
user sees the full progress panel, messages & tools panel, and current report
in real time. The interactive wizard is bypassed by monkey-patching
get_user_selections(); the trailing "Save report?" / "Display full report?"
prompts are auto-answered with their defaults so the run completes without
needing keyboard input.

Usage:
    python scripts/run_ticker_ui.py <TICKER> [YYYY-MM-DD]

Intended to run inside a tmux session so progress is visible whether or not
the user is currently attached.
"""

from __future__ import annotations

import os
import datetime
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Load .env / .env.enterprise so Azure creds + LOGID are present.
try:
    from dotenv import load_dotenv

    for fname in (".env", ".env.enterprise"):
        candidate = REPO_ROOT / fname
        if candidate.exists():
            load_dotenv(candidate)
except ImportError:
    pass

import cli.main  # noqa: E402
from cli.main import save_report_to_disk  # noqa: E402
from cli.models import AnalystType  # noqa: E402


FIXED_ANALYSTS = [
    AnalystType.MARKET,
    AnalystType.SOCIAL,
    AnalystType.NEWS,
    AnalystType.FUNDAMENTALS,
]
FIXED_MODEL = "gpt-5.5-2026-04-24"
# Wizard returns the provider *key* ("azure"), not the display name ("Azure OpenAI").
# run_analysis() lowercases this and the factory matches on the key.
FIXED_PROVIDER = "azure"
FIXED_DEPTH = 5  # "Deep" — matches cli/utils.py:112
FIXED_LANGUAGE = "English"


def _kill_own_tmux_session(ticker: str) -> None:
    """If we're inside the tmux session this run spawned, kill it.

    Called on successful completion so the wrapper's watch mode auto-cleans
    when the report is written — mirroring the headless mode's PID-file
    cleanup. Crash paths skip this so the session stays alive for the user
    to inspect any traceback in the pane.

    Only kills sessions matching the expected naming convention
    (`ta-<ticker-lower>`) so an unrelated tmux session never gets clobbered.
    """
    import subprocess

    if not os.environ.get("TMUX"):
        return  # not running inside tmux at all

    expected = f"ta-{ticker.lower()}"
    try:
        current = subprocess.check_output(
            ["tmux", "display-message", "-p", "#S"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return

    if current != expected:
        return  # different session — leave it alone

    # kill-session detaches all clients and tears down the pty; our own
    # process gets SIGHUP shortly after as a side effect, which is fine —
    # all useful work (report saved, prompts auto-answered) is already done.
    subprocess.run(
        ["tmux", "kill-session", "-t", expected],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in {"-h", "--help"}:
        print(__doc__)
        return 0 if len(argv) >= 2 else 2

    ticker = argv[1].strip().upper()
    if len(argv) >= 3 and argv[2]:
        try:
            datetime.date.fromisoformat(argv[2])
        except ValueError:
            print(f"Invalid date '{argv[2]}'. Expected YYYY-MM-DD.", file=sys.stderr)
            return 2
        date = argv[2]
    else:
        date = datetime.date.today().isoformat()

    # Pre-built selections dict mirroring what get_user_selections() returns.
    selections = {
        "ticker": ticker,
        "analysis_date": date,
        "output_language": FIXED_LANGUAGE,
        "analysts": FIXED_ANALYSTS,
        "research_depth": FIXED_DEPTH,
        "llm_provider": FIXED_PROVIDER,
        "backend_url": None,  # Azure reads endpoint from AZURE_OPENAI_ENDPOINT env var
        "shallow_thinker": FIXED_MODEL,
        "deep_thinker": FIXED_MODEL,
        "google_thinking_level": None,
        "openai_reasoning_effort": None,
        "anthropic_effort": None,
    }

    # Bypass the interactive wizard.
    cli.main.get_user_selections = lambda: selections

    # Auto-answer the post-run "Save report?" / "Save path?" / "Display full
    # report?" prompts so the run completes unattended. Each prompt has a
    # sensible default; we just return it.
    original_prompt = cli.main.typer.prompt

    def auto_prompt(text, *args, **kwargs):
        default = kwargs.get("default")
        if default is None and args:
            default = args[0]
        return default if default is not None else "Y"

    cli.main.typer.prompt = auto_prompt

    # Capture final_state by intercepting cli.main.save_report_to_disk.
    # run_analysis() doesn't return final_state, and its internal save uses
    # Path.cwd() for the destination — which lands in the wrong place when
    # this script runs from a tmux session whose cwd isn't the repo root.
    # The stub records final_state without writing, then we re-invoke the
    # real save_report_to_disk below pointing at <repo>/reports/<TICKER>_<TS>/
    # to mirror scripts/run_ticker.py's behavior.
    captured: dict = {}

    def capture_only(final_state, _ticker, save_path):
        captured["final_state"] = final_state
        return save_path / "complete_report.md"

    cli.main.save_report_to_disk = capture_only

    try:
        cli.main.run_analysis(checkpoint=True)
    finally:
        cli.main.typer.prompt = original_prompt
        cli.main.save_report_to_disk = save_report_to_disk

    # Success only. If run_analysis raised, we already returned above (via
    # the finally re-raising) and don't reach this line — leaving the tmux
    # session alive so the user can see the traceback.

    # Write the consolidated report into <repo>/reports/<TICKER>_<TS>/ using
    # the same function scripts/run_ticker.py uses, before tmux cleanup so a
    # crash there doesn't lose the report.
    if "final_state" in captured:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_dir = REPO_ROOT / "reports" / f"{ticker}_{timestamp}"
        save_report_to_disk(captured["final_state"], ticker, report_dir)

    _kill_own_tmux_session(ticker)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

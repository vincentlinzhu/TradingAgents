#!/usr/bin/env python3
"""Headless TradingAgents runner.

Fixed config: Azure OpenAI, gpt-5.5-2026-04-24 (deep + quick), Deep research
depth, all 4 analysts (market/social/news/fundamentals), English, checkpoint
enabled. Only the ticker (and optionally the analysis date) is variable.

Usage:
    python scripts/run_ticker.py <TICKER> [YYYY-MM-DD]

The date defaults to today's date in ISO format. Reports are written to
<repo>/reports/<TICKER>_<TIMESTAMP>/ and a structured log is written to
~/.tradingagents/logs/<TICKER>/<DATE>/headless.log
"""

from __future__ import annotations

import datetime
import logging
import os
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Make the editable repo importable when invoked without the package context.
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

from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402
from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402
from cli.main import save_report_to_disk  # noqa: E402


FIXED_ANALYSTS = ["market", "social", "news", "fundamentals"]
FIXED_MODEL = "gpt-5.5-2026-04-24"
FIXED_PROVIDER = "azure"
FIXED_DEPTH = 5  # "Deep" — matches cli/utils.py:112
FIXED_LANGUAGE = "English"


def _setup_logging(ticker: str, date: str) -> Path:
    """Configure root logger to write timestamped lines to a per-run log file."""
    home = Path(os.environ.get("TRADINGAGENTS_HOME", str(Path.home() / ".tradingagents")))
    log_dir = home / "logs" / ticker.upper() / date
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "headless.log"

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Clear any prior handlers (e.g. when invoked repeatedly in one process).
    root.handlers.clear()

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    root.addHandler(stream_handler)

    return log_file


def _build_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = FIXED_PROVIDER
    config["deep_think_llm"] = FIXED_MODEL
    config["quick_think_llm"] = FIXED_MODEL
    config["max_debate_rounds"] = FIXED_DEPTH
    config["max_risk_discuss_rounds"] = FIXED_DEPTH
    config["output_language"] = FIXED_LANGUAGE
    config["checkpoint_enabled"] = True
    return config


def _cleanup_pid_file(ticker: str, log: logging.Logger) -> None:
    """Remove our PID file if it still points at our parent (caffeinate).

    Called from a `finally` block in main() so it fires on every exit path —
    success, expected returns (1, 130), and unhandled exceptions. The PPID
    match guards against a concurrent --force run having overwritten the
    file with its own PID since we started.
    """
    home = Path(os.environ.get("TRADINGAGENTS_HOME", str(Path.home() / ".tradingagents")))
    pid_file = home / "run_state" / f"{ticker}.pid"
    if not pid_file.exists():
        return
    try:
        stored_pid = int(pid_file.read_text().strip())
        if stored_pid == os.getppid():
            pid_file.unlink()
            log.info("PID file cleared: %s", pid_file)
    except (ValueError, OSError):
        pass  # stale/unreadable — wrapper's stale-PID detection will handle next time


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

    log_file = _setup_logging(ticker, date)
    log = logging.getLogger("run_ticker")

    log.info("=" * 72)
    log.info("TradingAgents headless run starting")
    log.info("  ticker:    %s", ticker)
    log.info("  date:      %s", date)
    log.info("  provider:  %s", FIXED_PROVIDER)
    log.info("  model:     %s (deep+quick)", FIXED_MODEL)
    log.info("  depth:     Deep (%d rounds)", FIXED_DEPTH)
    log.info("  analysts:  %s", ", ".join(FIXED_ANALYSTS))
    log.info("  language:  %s", FIXED_LANGUAGE)
    log.info("  checkpoint: enabled")
    log.info("  log file:  %s", log_file)
    log.info("=" * 72)

    config = _build_config()

    try:
        try:
            graph = TradingAgentsGraph(FIXED_ANALYSTS, config=config, debug=False)
        except Exception:
            log.error("Failed to construct TradingAgentsGraph:\n%s", traceback.format_exc())
            return 1

        log.info("Graph constructed. Calling propagate() — this may take 30-90+ minutes.")

        try:
            final_state, signal = graph.propagate(ticker, date)
        except KeyboardInterrupt:
            log.warning("Interrupted by user. Checkpoint state preserved on disk.")
            return 130
        except Exception:
            log.error("propagate() raised:\n%s", traceback.format_exc())
            log.error("Checkpoint state preserved — rerun the same command to resume.")
            return 1

        log.info("propagate() completed. Final signal: %s", signal)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_dir = REPO_ROOT / "reports" / f"{ticker}_{timestamp}"
        try:
            report_file = save_report_to_disk(final_state, ticker, report_dir)
        except Exception:
            log.error("Report save failed:\n%s", traceback.format_exc())
            log.error("Final state available in graph object but not written to disk.")
            return 1

        log.info("Report saved: %s", report_file)
        log.info("Report dir:   %s", report_dir)
        log.info("Run complete. Final decision: %s", signal)
        return 0
    finally:
        _cleanup_pid_file(ticker, log)


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env bash
# Quick status check for a headless tradingagents run.
# Usage: ta_check.sh <TICKER> <DATE>
set -uo pipefail
TICKER="$1"
DATE="${2:-$(date +%Y-%m-%d)}"
REPO="/Users/bytedance/Documents/opensource/TradingAgents"
PIDF="$HOME/.tradingagents/run_state/${TICKER}.pid"
LOG="$HOME/.tradingagents/logs/${TICKER}/${DATE}/headless.log"

alive=0
if [[ -f "$PIDF" ]]; then
  PID="$(cat "$PIDF" 2>/dev/null)"
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then alive=1; fi
fi
echo "ticker=$TICKER pid=$(cat "$PIDF" 2>/dev/null) alive=$alive"

# Report dir (today) in reports/ or archive/reports_<date>/
rep="$(ls -d ${REPO}/reports/${TICKER}_* 2>/dev/null | tail -1)"
arc="$(ls -d ${REPO}/archive/reports_${DATE//-/}/${TICKER}_* 2>/dev/null | tail -1)"
for d in "$rep" "$arc"; do
  [[ -n "$d" ]] || continue
  if [[ -f "$d/complete_report.md" ]]; then
    echo "COMPLETE: $d ($(du -h "$d/complete_report.md" | cut -f1))"
  else
    echo "partial dir: $d (no complete_report.md)"
  fi
done

echo "--- decision line (if any) ---"
grep -iE "Run complete|Final decision|FINAL TRANSACTION|propagate\(\) raised|Traceback|403|PermissionDenied" "$LOG" 2>/dev/null | tail -5
echo "--- last log line ---"
tail -1 "$LOG" 2>/dev/null | cut -c1-90

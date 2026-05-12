# Execution Guide: When to Run, How Orders Work

A practical guide for turning the framework's reports into real trades without getting caught by mid-session noise or overnight gaps.

---

## When the trading day actually ends

US stock markets have **three** sessions, and "the day ended" can mean any of them:

| Session | Hours (ET) | What happens |
| --- | --- | --- |
| Pre-market | 4:00 am – 9:30 am | Light volume, wide spreads, news reactions |
| **Regular session** | **9:30 am – 4:00 pm** | The "real" market — what the daily bar reflects |
| After-hours | 4:00 pm – 8:00 pm | Light volume, earnings reactions, etc. |

When CNBC says "stocks closed at...", they mean the **4:00 pm ET closing auction print**. That's the number that becomes the official `Close` in every daily-bar dataset including yfinance.

After-hours trading still happens (and you'll see prices move on Yahoo Finance after 4 pm), but those trades **do not change today's close**. They're separate, lightly-traded sessions. They *do* hint at where tomorrow might open, though — which is the next thing you need to understand.

**Recommendation: run the framework around 4:30 pm ET or later.**

Why not 4:01 pm: yfinance's daily bar takes a few minutes to settle after the closing auction. Running at 4:30 pm guarantees you're getting the finalized bar, not a half-updated one. Running anytime that evening (5pm, 8pm, midnight) is fine — the daily bar is locked in, and the report will be reproducible until the next session opens.

If you're outside ET, the equivalents:

- PT (California): **1:30 pm**
- CT (Chicago): **3:30 pm**
- UTC: **20:30** (21:30 during US daylight saving)
- Beijing/Singapore: **4:30 am the next day** (5:30 am during DST)

---

## How overnight orders work

This is the part that surprises people. Three things to internalize.

### 1. Most overnight orders execute at the *open*, not at last night's price

If at 9 pm you see UFO at 51.50 and place a regular order, **it doesn't execute at 51.50.** Unless you're using extended-hours trading (see below), your order sits in a queue until the market opens at 9:30 am the next morning. It then fills at whatever the **opening price** is — which is set by the opening auction at 9:30 am and can be very different from last night's close.

This difference is called a **gap**:

- Stock closes at 54.50, opens next morning at 56.20 → "gap up" of 1.70 (often on good news overnight)
- Stock closes at 54.50, opens next morning at 52.10 → "gap down" of 2.40 (often on bad news)

Gaps happen because **all the demand and information from 16 hours of off-hours news gets crammed into the opening price**. Earnings reports, Fed announcements, geopolitical events, sector moves overseas — all of it expresses through the opening auction.

### 2. Order types control what price you actually get

This is the lever you use to manage gap risk:

- **Market order** — "fill me at whatever price exists when I'm next in line." Cheap, fast, dangerous on gaps. If UFO gaps from 51.50 to 55, your buy fills at ~55. You wanted 51.50, you got 55. Don't use market orders overnight on volatile names.
- **Limit order** — "buy at 52 or lower, sell at 56 or higher." Gives you price control. If UFO gaps up to 55, your 52 buy *doesn't fill* — you missed the trade rather than overpaying. If it gaps down to 51.50, you fill at 51.50 (or better — sometimes the open is below your limit and you get an even better price). **Use limit orders for overnight placement.**
- **Stop order** — "if UFO falls to 49, sell at market." Used as protection on positions you already own. Same gap risk: if UFO gaps from 50 to 47, your stop triggers and fills at ~47, not 49. Hence "stop loss" doesn't really cap loss on gaps.
- **Stop-limit order** — combines both: "if UFO falls to 49, place a limit order at 48.50." Better gap control, but if it gaps below 48.50, your order doesn't fill at all and you keep falling.

### 3. The price you "see" overnight is not the price you'll get

Yahoo Finance's after-hours price is real — *trades are happening at it* — but only if your broker supports extended-hours trading and you explicitly opt in. By default, your overnight order sits on the bench until 9:30 am.

Some brokers (IBKR, Schwab, Fidelity, Robinhood) let you toggle "extended hours" on individual orders. If you do, your order can execute pre-market (4–9:30 am) or after-hours (4–8 pm) at those displayed prices — but **liquidity is thin, spreads are wide, and a 50-share trade can move the price 1–2%**. Generally not worth it unless you have a specific reason.

---

## Putting it together: the workflow

The most disciplined approach for using these reports:

1. **Run the framework at 4:30 pm ET or later.** You get a clean daily bar and a stable report.
2. **Read the report's specific triggers.** The UFO report named: *add above 55.90 close on volume, add on pullback to 52.00–52.15 that holds, exit below 49.0.*
3. **Decide which trigger you want to act on.** You don't have to act tonight at all — many days, no trigger is hit.
4. **If you want to act, place a limit order tied to a trigger.** Examples:
   - `Buy 100 UFO limit 52.10 GTC` — meaning "I'll buy at 52.10 or lower; keep this order alive until I cancel." Sits on the book; only fills if price drops to your level.
   - `Sell 100 UFO stop 49.00` — protects your position if UFO breaks the invalidation level.
5. **Re-evaluate the next evening with a fresh run.** Each day's bar updates the analysis; old triggers may shift.

---

## A concrete example

You see UFO at 51.50 in after-hours and want to buy:

- **Don't** place a market order — you'll fill at the open, which could be anything.
- **Do** place a limit order at, say, 52.00 GTC. Three outcomes the next morning:
  1. UFO opens at 51.80 → you fill at 51.80 (your limit said "52 or lower"; the open was lower, so you got an even better price).
  2. UFO opens at 52.00 → you fill at 52.00 exactly.
  3. UFO opens at 53.50 → your order doesn't fill. You can cancel and reassess, or leave the GTC and hope it pulls back to 52 later in the day.

That's how you turn an evening report into a disciplined morning execution without getting blindsided by a gap.

---

## What the framework actually pulls (intraday caveat)

If you ever run the framework mid-session, know that:

- All data is **daily OHLCV bars** — yfinance and Alpha Vantage both default to one row per trading day. There is no intraday plumbing.
- Today's bar is **partial mid-session**. The `Close` is just the last trade price at the moment of the query, the `High`/`Low` are running extremes so far, and `Volume` reflects only what's traded so far that day.
- Every indicator (RSI, MACD, EMA, SMA, VWMA) is computed off that partial bar as if it were a finished one. Results will shift hour-to-hour.
- The OHLCV cache is keyed by today's date, so two intraday runs may reuse stale data without you noticing. Delete the cached CSV in `data_cache_dir` to force a refresh.

Bottom line: **the report is designed for end-of-day use.** Mid-day runs are best treated as "what would I think if today closed right now" — a hypothetical, not a forecast.

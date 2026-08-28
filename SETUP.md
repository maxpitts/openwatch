# Setup

## 0. Take the baseline first — today

Everything below is recoverable at any time. The baseline is not: you cannot go back and measure
what the Hub looked like this week. The deal was reported 27 Aug 2026, so a snapshot dated now is
worth far more than a better-engineered one dated next month.

Run this in your own Terminal (stdlib only, no deps, no key):

```bash
python3 snapshot.py --top 5000 --out data/$(date -u +%F).json
python3 metrics.py --snapshot data/$(date -u +%F).json --series data/metrics.json
```

Takes a few minutes. If it works, you're done with the part that has a deadline.

## 1. Public repo

It must be **public**. Private turns this into a private dashboard, and the whole accountability
claim rests on anyone being able to run `git log -- data/`.

```bash
git init && git add -A && git commit -m "openwatch: baseline"
gh repo create openwatch --public --source=. --push
```

## 2. Enable the Action to write

**Settings → Actions → General → Workflow permissions → "Read and write permissions".**

Skip this and the daily run goes green while committing nothing — the failure is silent, which is
the worst kind. No secrets are needed; `GITHUB_TOKEN` covers the push.

## 3. Verify it runs

Actions → **Daily snapshot** → Run workflow. Confirm a `snapshot YYYY-MM-DD` commit appears. From
then on it's 06:17 UTC daily and needs nothing from you.

## 4. Optional: rate limit

Unauthenticated works fine at 5,000 models. If you push to 50,000, add an `HF_TOKEN` repo secret
(a read-only token) — `snapshot.py` picks it up automatically.

## Then leave it alone

Thirty days of snapshots is when this stops being a gesture and becomes evidence. Don't publish
weekly "nothing happened" posts — that trains people to ignore you. The publishing trigger is the
first CRITICAL event, and it works precisely because you were boring for six weeks first.

Note the deal is reported and agreed, not closed, and faces antitrust review. Keep capturing
through that: a deal that gets blocked is also a finding, and you'll have the only before-and-after.

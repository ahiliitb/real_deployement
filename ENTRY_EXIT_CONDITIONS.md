# Potential Entry & Exit — Conditions

Conditions applied by `utils.entry_exit_fetcher` to build `potential_entry.csv` and `potential_exit.csv`.

## Potential Entry

All must hold:

| Condition | Rule |
|-----------|------|
| Signal type | Long only |
| Win rate | > 80% |
| Number of trades | > 6 |
| Exit status | "No Exit Yet" |
| Price band | Today's price between -3% and +1% vs signal price |
| PE ratio | < 50 and Industry PE > PE ratio |
| Profit trend | Last quarter profit > 50% of same quarter last year |
| Trendline only | TrendPulse start price > end price |

## Potential Exit

All must hold:

| Condition | Rule |
|-----------|------|
| Signal type | Long only |
| Win rate | > 80% |
| Number of trades | > 6 |
| Exit status | Exit signal present (not "No Exit Yet") |
| Exit recency | Exit date within last 3 days of fetch date |
| PE ratio | < 50 and Industry PE > PE ratio |
| Profit trend | Last quarter profit > 50% of same quarter last year |
| Trendline only | TrendPulse start price > end price |

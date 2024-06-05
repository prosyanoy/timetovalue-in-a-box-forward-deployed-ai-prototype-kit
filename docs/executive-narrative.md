# From event stream to first insight: executive summary

*A customer-facing one-pager, written the way a forward-deployed engineer would hand it over after a prototype session. Figures come from the kit's synthetic network-anomaly pack; every assumption is a stated, editable input.*

## The question we set out to answer

How quickly can your team see value from AI on your own event data, and is that value worth pursuing?

## What we did

We stood up the full pipeline (event bus, telemetry collector, scoring service, dashboard) on a laptop-sized Kubernetes cluster with a single command. The kit started a stopwatch before the first cluster command and stopped it when the first plain-English insight reached the dashboard. That number is **time to first insight**, and the kit reports it on every run (`make up` prints it, the dashboard displays it). Nothing was hand-tuned between runs, and swapping to a different industry scenario is one setting (`SCENARIO=predictive-maintenance`).

## What we found

| Measure | Result in the demo run | Why it matters |
|---|---|---|
| Time to first insight | **0.7 s** after the pipeline started (in-process demo; the cluster figure is printed by `make up`) | How fast a pilot becomes tangible |
| Detection latency | **under 1 ms** from event to insight | Anomalies are surfaced while they are still actionable |
| Recall on injected anomalies | **94–100%** on the demo samples | Few real problems missed |
| False-positive share of alerts | **about 11%**, against 85% assumed today | Analysts stop chasing noise |

Each alert is written for a non-specialist, for example: *"CRITICAL: host gw-05 shows possible data exfiltration. Outbound traffic 2,461 KB/min (11.1σ above normal). Suggested action: isolate the host from external egress and review recent file access."*

## What it is worth (illustrative)

Assuming 40 genuine incidents a month, 4 hours to notice each one today, 1,500 alerts a month of which 85% are false, 12 minutes of triage per alert, an analyst cost of USD 85/hour and USD 450 for every hour an incident goes unnoticed:

- **about 414 analyst and exposure hours saved per month**
- **about USD 94,000 per month, or about USD 1.1 million per year**

Roughly 160 of those hours come from shorter exposure and the rest from fewer false alerts to triage. Savings are counted only for anomalies the kit actually catches; missed ones earn nothing, and the estimate drops accordingly if recall or precision fall.

## How to read these numbers

- The data is synthetic. The speed and pipeline figures are real measurements of the platform; the accuracy figures describe the demo generator, not your environment.
- Cost assumptions are placeholders to be replaced with your own. The dashboard's ROI panel recalculates instantly (`make roi` does the same from the command line).

## Proposed next step

A two-week pilot on a copy of one real data feed: replace the synthetic generator with your stream, keep the same pipeline, and re-measure all four numbers above against your own baseline. The decision at the end is a quantified one, not a demo impression.

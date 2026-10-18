# Demo workspace (synthetic data)

Everything in this folder is fictional and exists only for the `demo` account:

- `profile.yaml` + `candidate_profile/` — the demo candidate ("Dana Demo"), used by career scoring.
- `knowledge_base/` — synthetic documents indexed for the demo workspace (one is in Hebrew to exercise multilingual search).
- `tracker_seed.yaml` — synthetic job-application rows for the tracker and dashboard.

`python scripts/seed_demo.py` loads it into the demo workspace idempotently. None of it is real personal data.

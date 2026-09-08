# Safe deployment and dispatch recovery

## Immutable artifact contract

Builds must set `BUILD_GIT_SHA` and `BUILD_TIMESTAMP`. Deployments must set
`EXPECTED_GIT_SHA` to the same full commit SHA. Startup fails when the expected
and running revisions differ. `/health` exposes the revision, deployment ID,
configuration validation, publication states, overdue packages, and stuck
transient-state count without exposing credentials.

## Railway rollout

1. Set `CONTENT_DISPATCH_ENABLED=false` and keep preparation enabled.
2. Deploy one immutable commit with `BUILD_GIT_SHA`, `BUILD_TIMESTAMP`, and
   `EXPECTED_GIT_SHA` supplied by CI/Railway.
3. Verify the running artifact:

   ```powershell
   python scripts/verify_deployment.py --url https://SERVICE.up.railway.app --expected-sha FULL_COMMIT_SHA
   ```

4. Inspect `/status`, `/can-this-post?outbox_id=...`, and the classified
   backlog. Expired, blocked, ambiguous, and reconciliation-required packages
   must not be bulk released.
5. Enable dispatch as a configuration-only change. Verify the revision again,
   then allow the worker to claim only `READY_TO_DISPATCH`,
   `PARTIALLY_PUBLISHED`, and `FAILED_DELIVERY` packages.
6. Disable dispatch immediately if the running SHA changes, startup validation
   reports a blocker, or stuck/ambiguous transaction counts increase.

Configuration changes do not rebuild creative packages, reset AI budgets,
clear reservations, or erase per-platform receipts. Never redeploy solely to
retry an uncertain platform request; reconcile the existing request key first.
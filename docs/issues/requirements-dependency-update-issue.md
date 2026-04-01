# Issue: Update `requirements.txt` dependency minimums

## Summary
Track a follow-up change to update dependency constraints in `requirements.txt` to the requested versions/ranges instead of applying the change directly in this PR.

## Requested dependency constraints
- `pillow>=10.2.0`
- `pyasn1>=0.6.3`
- `protobuf>=4.25.8,<5`
- `h11>=0.16.0`
- `zipp>=3.19.1`
- `urllib3>=2.5.0,<3`
- `requests>=2.32.4,<3`
- `numpy>=1.22.2`

## Why this issue exists
A previous PR directly implemented the dependency changes, but the request was to open an issue first and tie implementation work to that issue.

## Scope for future PR
1. Update `requirements.txt` with the requested constraints.
2. Run relevant lint/test checks.
3. Validate compatibility for `protobuf` downgrade to `<5`.
4. Reference this issue in the implementation PR.

## Linkage
- Related PR: Update dependency constraints in requirements.txt

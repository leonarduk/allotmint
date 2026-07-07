# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in AllotMint, please report it
privately rather than opening a public issue.

- Preferred: use [GitHub's private vulnerability reporting](https://github.com/leonarduk/allotmint/security/advisories/new)
  for this repository.
- Alternative: email the maintainer directly with details of the issue.

Please include as much of the following as you can:

- A description of the vulnerability and its potential impact.
- Steps to reproduce, or a proof-of-concept.
- The affected component (backend, frontend, CDK/infrastructure, etc.) and
  version/commit.

You should receive an acknowledgement within a few days. We'll work with you
to understand and confirm the issue, and will let you know when a fix has
shipped. Please give us a reasonable amount of time to address the issue
before any public disclosure.

## Supported Versions

AllotMint is deployed continuously from the `main` branch; there are no
maintained release branches or long-term support versions. Security fixes are
applied to `main` and deployed as part of the normal release process.

## Scope

For details on the deployed application's authentication model, Content
Security Policy, and known trust-boundary risks, see
[docs/SECURITY.md](../docs/SECURITY.md).

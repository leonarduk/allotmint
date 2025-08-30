# Backend Dependency Upgrade Notes

This release updates backend dependencies to their latest stable versions.

## Breaking API Changes

- **lxml 6.0.0**: drops support for Python versions earlier than 3.8 and removes `MemDebug.dump()` and `MemDebug.show()`. The `Schematron` class is now deprecated and will be removed in a future release.
- **cryptography 45.0.6**: `load_ssh_private_key` now raises a `TypeError` if a password is provided for an unencrypted key or omitted for an encrypted key.

No other breaking API changes were identified.

# Changelog

All notable changes to this project are documented in this file. Earlier releases: the git history.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.4] - 2026-10-28

### Security

- Keyless HTTP is now refused by default even for loopback sockets owned by the server's user: arbitrary same-user proxies and tunnels are indistinguishable from direct clients. Set a bearer key for normal HTTP use. `AIMARKET_MCP_LOCAL_RELAY=1` explicitly trusts local TCP callers, including such relays; the caller must still pass loopback Host/peer, Origin, forwarding-header and socket-owner checks. Where Linux socket tables are absent, `AIMARKET_MCP_LOCAL_UNVERIFIED=1` is additionally required. Removed process-name/listener heuristics that missed multiprocess proxies. Closes Vulnetix GCVE-110-VULN-PYPI-2026-000640.

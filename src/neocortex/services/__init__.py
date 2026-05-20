"""Pure function service layer for HTTP server / future GUI consumption.

Per CLIENT_PROPOSAL.md v0.7 Sprint 0 (option C 渐进式): this layer wraps and
re-uses CLI internals from ``neocortex.cmd_*`` without modifying them. CLI
keeps working unchanged; server gets a clean console-free entry point.
After GUI is validated and stable, CLI will collapse onto these services
as a single source of truth.
"""

"""Additive agents for the Infenergy social engine.

Each module exposes a top-level `run(data_dir: str, **kwargs) -> dict` function
that returns a JSON-serializable payload and (where relevant) writes a
timestamped snapshot to `data/agents/<agent_name>/`.

Agents are intentionally decoupled from the main content pipeline: they can be
invoked ad-hoc via the worker endpoint or scheduled independently, and each
degrades gracefully when its data source (engagement API, RSS feed, Gemini,
etc.) is unavailable.
"""

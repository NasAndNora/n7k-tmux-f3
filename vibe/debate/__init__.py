"""Multi-AI debate module - routes messages between Claude and Gemini."""

from __future__ import annotations

from vibe.debate.routing import ROUTING_TAGS, build_context, parse_routing_tag

__all__ = ["ROUTING_TAGS", "build_context", "parse_routing_tag"]

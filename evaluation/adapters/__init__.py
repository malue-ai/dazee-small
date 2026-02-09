"""
Evaluation adapters - bridge between harness and external agents.

HttpAgentAdapter: call ZenFlux HTTP API (POST /chat, poll session, fetch messages)
and return Transcript-compatible dict for the evaluation harness.
"""

from evaluation.adapters.http_agent import HttpAgentAdapter

__all__ = ["HttpAgentAdapter"]

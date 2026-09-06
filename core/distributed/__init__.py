"""
Brahma Distributed Architecture Package
Enables separation between Cloud Brain (Conversations & Multimodal Live Engine)
and Local Worker Nodes (Desktop Automation & Task Execution).
"""

from .protocol import ProtocolTypes, MessageEnvelope, build_message, parse_message

__all__ = ["ProtocolTypes", "MessageEnvelope", "build_message", "parse_message"]

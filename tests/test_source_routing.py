"""Tests for source-first routing guidance in the system prompt."""

import pytest

from agent.prompt_builder import SOURCE_ROUTING_GUIDANCE


class TestSourceRoutingConstant:
    """Verify the SOURCE_ROUTING_GUIDANCE constant exists and contains expected rules."""

    def test_constant_exists(self):
        assert SOURCE_ROUTING_GUIDANCE is not None
        assert isinstance(SOURCE_ROUTING_GUIDANCE, str)
        assert len(SOURCE_ROUTING_GUIDANCE) > 0

    def test_contains_header(self):
        assert "Source-first routing" in SOURCE_ROUTING_GUIDANCE

    def test_contains_x_twitter_rule(self):
        assert "x.com" in SOURCE_ROUTING_GUIDANCE
        assert "twitter.com" in SOURCE_ROUTING_GUIDANCE
        assert "xurl read" in SOURCE_ROUTING_GUIDANCE

    def test_contains_youtube_rule(self):
        assert "youtube.com" in SOURCE_ROUTING_GUIDANCE
        assert "youtu.be" in SOURCE_ROUTING_GUIDANCE
        assert "transcript" in SOURCE_ROUTING_GUIDANCE

    def test_contains_github_rule(self):
        assert "github.com" in SOURCE_ROUTING_GUIDANCE
        assert "gh CLI" in SOURCE_ROUTING_GUIDANCE or "git" in SOURCE_ROUTING_GUIDANCE

    def test_contains_pdf_rule(self):
        assert "PDF" in SOURCE_ROUTING_GUIDANCE
        assert "web_extract" in SOURCE_ROUTING_GUIDANCE or "document extraction" in SOURCE_ROUTING_GUIDANCE

    def test_contains_general_rule(self):
        assert "native tool" in SOURCE_ROUTING_GUIDANCE
        assert "Do not search" in SOURCE_ROUTING_GUIDANCE or "Do NOT search" in SOURCE_ROUTING_GUIDANCE


class TestSourceRoutingInSystemPrompt:
    """Verify SOURCE_ROUTING_GUIDANCE is importable in run_agent and
    would be included in system prompt assembly."""

    def test_importable_from_run_agent(self):
        """run_agent.py imports SOURCE_ROUTING_GUIDANCE alongside other guidance."""
        from run_agent import SOURCE_ROUTING_GUIDANCE as imported
        assert imported is SOURCE_ROUTING_GUIDANCE

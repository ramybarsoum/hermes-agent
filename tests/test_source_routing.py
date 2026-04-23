"""Tests for source-first routing guidance in the system prompt."""

import pytest
from unittest.mock import patch, MagicMock

from agent.prompt_builder import SOURCE_ROUTING_GUIDANCE, build_source_routing_guidance


class TestSourceRoutingConstant:
    """Verify the SOURCE_ROUTING_GUIDANCE static fallback constant."""

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


class TestDynamicBuilder:
    """Verify build_source_routing_guidance() produces valid output."""

    def test_returns_string(self):
        result = build_source_routing_guidance()
        assert isinstance(result, str)

    def test_contains_header(self):
        result = build_source_routing_guidance()
        assert "# Source-first routing" in result

    def test_contains_general_rule(self):
        result = build_source_routing_guidance()
        assert "native tool" in result
        assert "Do not search" in result

    def test_includes_default_domains(self):
        """When config loads successfully, all default domain rules appear."""
        result = build_source_routing_guidance()
        # These should appear whether from config or fallback
        assert "x.com" in result
        assert "youtube.com" in result
        assert "github.com" in result

    def test_new_domains_present(self):
        """New domains from default config should appear in dynamic output."""
        result = build_source_routing_guidance()
        assert "docs.google.com" in result
        assert "notion.so" in result
        assert "linear.app" in result

    def test_google_workspace_tool(self):
        result = build_source_routing_guidance()
        assert "google-workspace" in result

    def test_notion_tool(self):
        result = build_source_routing_guidance()
        assert "notion API" in result

    def test_linear_tool(self):
        result = build_source_routing_guidance()
        assert "linear CLI" in result

    def test_empty_when_disabled(self):
        """When routing.enabled=False, the builder returns an empty string."""
        mock_config = {
            "routing": {
                "enabled": False,
                "domain_rules": {"x.com": {"tool": "xurl read"}},
            }
        }
        with patch("hermes_cli.config.load_config", return_value=mock_config):
            result = build_source_routing_guidance()
            assert result == ""

    def test_fallback_on_config_error(self):
        """When config loading fails entirely, fallback defaults are used."""
        with patch("hermes_cli.config.load_config", side_effect=Exception("no config")):
            result = build_source_routing_guidance()
            assert isinstance(result, str)
            assert "x.com" in result
            assert "youtube.com" in result
            assert "github.com" in result

    def test_empty_domain_rules_returns_empty(self):
        """When domain_rules is empty, the builder returns an empty string."""
        mock_config = {
            "routing": {
                "enabled": True,
                "domain_rules": {},
            }
        }
        with patch("hermes_cli.config.load_config", return_value=mock_config):
            result = build_source_routing_guidance()
            assert result == ""

    def test_custom_domain_rule(self):
        """A user-added domain rule should appear in the output."""
        mock_config = {
            "routing": {
                "enabled": True,
                "domain_rules": {
                    "example.com": {"tool": "example-tool"},
                },
            }
        }
        with patch("hermes_cli.config.load_config", return_value=mock_config):
            result = build_source_routing_guidance()
            assert "example.com" in result
            assert "example-tool" in result

    def test_no_routing_key_returns_empty(self):
        """When routing key is missing entirely, returns empty string."""
        mock_config = {}
        with patch("hermes_cli.config.load_config", return_value=mock_config):
            result = build_source_routing_guidance()
            assert result == ""


class TestSourceRoutingInSystemPrompt:
    """Verify SOURCE_ROUTING_GUIDANCE is importable in run_agent and
    would be included in system prompt assembly."""

    def test_importable_from_run_agent(self):
        """run_agent.py imports SOURCE_ROUTING_GUIDANCE alongside other guidance."""
        from run_agent import SOURCE_ROUTING_GUIDANCE as imported
        assert imported is SOURCE_ROUTING_GUIDANCE

    def test_build_function_importable(self):
        """run_agent.py imports build_source_routing_guidance."""
        from run_agent import build_source_routing_guidance as imported
        assert callable(imported)

    def test_dynamic_or_fallback_is_string(self):
        """The routing_guidance = build_source_routing_guidance() or SOURCE_ROUTING_GUIDANCE
        pattern always yields a non-empty string."""
        guidance = build_source_routing_guidance() or SOURCE_ROUTING_GUIDANCE
        assert isinstance(guidance, str)
        assert len(guidance) > 0

"""Tests for Phase 3: strategy guidance injection into ephemeral_system_prompt.

Verifies:
1. _build_strategy_guidance returns None when no strategies are promoted
2. _build_strategy_guidance returns formatted guidance when strategies exist
3. Guidance is appended to ephemeral_system_prompt at agent init
4. Guidance handles strategies with config_json guidance text
5. Guidance is not injected when session_db is None
"""

import json
import time
import pytest
from unittest.mock import MagicMock, patch


def _make_session_db_with_strategies(strategies=None):
    """Create a mock SessionDB with get_promoted_strategies returning given list."""
    db = MagicMock()
    db.get_promoted_strategies.return_value = strategies or []
    return db


def _make_agent(session_db=None, ephemeral=None):
    """Create a minimal AIAgent for testing strategy guidance."""
    with (
        patch("run_agent.get_tool_definitions", return_value=[]),
        patch("run_agent.check_toolset_requirements", return_value={}),
        patch("run_agent.OpenAI"),
    ):
        from run_agent import AIAgent
        a = AIAgent(
            model="test-model",
            api_key="test-key-strategy",
            base_url="https://example.test/v1",
            provider="custom",
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
            session_db=session_db,
            ephemeral_system_prompt=ephemeral,
        )
        return a


class TestBuildStrategyGuidance:
    """_build_strategy_guidance unit tests."""

    def test_returns_none_when_no_session_db(self):
        a = _make_agent(session_db=None)
        assert a._build_strategy_guidance() is None

    def test_returns_none_when_no_promoted_strategies(self):
        db = _make_session_db_with_strategies([])
        a = _make_agent(session_db=db)
        # _build_strategy_guidance reads from session_db directly
        assert a._build_strategy_guidance() is None

    def test_returns_none_on_db_error(self):
        db = MagicMock()
        db.get_promoted_strategies.side_effect = Exception("db broken")
        a = _make_agent(session_db=db)
        assert a._build_strategy_guidance() is None

    def test_formats_single_strategy(self):
        db = _make_session_db_with_strategies([{
            "name": "prefer_parallel",
            "description": "Use concurrent reads",
            "score": 0.85,
            "sample_count": 50,
            "config_json": None,
        }])
        a = _make_agent(session_db=db)
        result = a._build_strategy_guidance()
        assert result is not None
        assert "prefer_parallel" in result
        assert "0.85" in result
        assert "n=50" in result
        assert "Use concurrent reads" in result

    def test_formats_multiple_strategies(self):
        db = _make_session_db_with_strategies([
            {"name": "strat_a", "description": "Do A", "score": 0.9, "sample_count": 30, "config_json": None},
            {"name": "strat_b", "description": "Do B", "score": 0.7, "sample_count": 25, "config_json": None},
        ])
        a = _make_agent(session_db=db)
        result = a._build_strategy_guidance()
        assert "strat_a" in result
        assert "strat_b" in result

    def test_includes_guidance_from_config_json(self):
        cfg = {"guidance": "Prefer read_file over terminal cat for file reading."}
        db = _make_session_db_with_strategies([{
            "name": "prefer_read_file",
            "description": "Use read_file",
            "score": 0.92,
            "sample_count": 100,
            "config_json": json.dumps(cfg),
        }])
        a = _make_agent(session_db=db)
        result = a._build_strategy_guidance()
        assert "Prefer read_file over terminal cat" in result


class TestStrategyGuidanceInjection:
    """Verify strategy guidance is appended to ephemeral_system_prompt at init."""

    def test_no_injection_when_no_promoted(self):
        db = _make_session_db_with_strategies([])
        a = _make_agent(session_db=db, ephemeral="base prompt")
        assert a.ephemeral_system_prompt == "base prompt"

    def test_injection_appends_to_existing(self):
        db = _make_session_db_with_strategies([{
            "name": "test_strat",
            "description": "A test strategy",
            "score": 0.8,
            "sample_count": 25,
            "config_json": None,
        }])
        a = _make_agent(session_db=db, ephemeral="base prompt")
        assert a.ephemeral_system_prompt.startswith("base prompt")
        assert "test_strat" in a.ephemeral_system_prompt

    def test_injection_without_existing_ephemeral(self):
        db = _make_session_db_with_strategies([{
            "name": "solo_strat",
            "description": "Only strategy",
            "score": 0.75,
            "sample_count": 40,
            "config_json": None,
        }])
        a = _make_agent(session_db=db, ephemeral=None)
        assert a.ephemeral_system_prompt is not None
        assert "solo_strat" in a.ephemeral_system_prompt

    def test_no_injection_without_session_db(self):
        a = _make_agent(session_db=None, ephemeral="just me")
        assert a.ephemeral_system_prompt == "just me"


class TestStrategyGuidanceWithRealDB:
    """Integration test using real SessionDB (in-memory)."""

    def test_full_round_trip(self, tmp_path):
        """Register → seed data → promote → create agent → verify guidance."""
        from hermes_state import SessionDB

        db_path = tmp_path / "test_strategy.db"
        real_db = SessionDB(db_path=db_path)

        # Register a strategy with guidance text
        real_db.register_strategy(
            "prefer_parallel_reads",
            description="Use concurrent tool execution for read-only batches",
            strategy_type="tool_ordering",
            baseline_latency_ms=500.0,
            config={"guidance": "When multiple read-only tools are called, execute them concurrently."},
        )

        # Seed enough data to pass promotion
        real_db.create_session(session_id="test-s1", source="cli")
        for _ in range(25):
            real_db.record_strategy_event(
                session_id="test-s1", event_type="tool_call",
                tool_name="read_file", strategy="prefer_parallel_reads",
                result="success", latency_ms=200.0,
            )
        for _ in range(2):
            real_db.record_strategy_event(
                session_id="test-s1", event_type="tool_call",
                tool_name="read_file", strategy="prefer_parallel_reads",
                result="failure", latency_ms=600.0,
            )

        # Promote
        verdict = real_db.promote_strategy("prefer_parallel_reads")
        assert verdict["can_promote"], f"Expected promotion, got: {verdict}"

        # Create agent with this DB
        a = _make_agent(session_db=real_db)
        assert a.ephemeral_system_prompt is not None
        assert "prefer_parallel_reads" in a.ephemeral_system_prompt
        assert "concurrent" in a.ephemeral_system_prompt.lower()
        real_db.close()

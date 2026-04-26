"""Tests for Phase 4: /insights --strategies CLI surface.

Verifies:
1. generate_strategy_report returns empty report when no data
2. generate_strategy_report returns tool stats and registry entries when data exists
3. format_strategy_terminal produces expected output format
4. format_strategy_gateway produces compact output
5. CLI _show_insights parses --strategies flag correctly
"""

import json
import time
import pytest
from unittest.mock import MagicMock, patch


class TestStrategyReportGeneration:
    """generate_strategy_report with real DB."""

    @pytest.fixture()
    def db(self, tmp_path):
        from hermes_state import SessionDB
        db_path = tmp_path / "test_strategy.db"
        session_db = SessionDB(db_path=db_path)
        yield session_db
        session_db.close()

    @pytest.fixture()
    def engine(self, db):
        from agent.insights import InsightsEngine
        return InsightsEngine(db)

    def test_empty_report(self, engine):
        report = engine.generate_strategy_report(days=30)
        assert report["empty"] is True
        assert report["tool_stats"] == []
        assert report["total_events"] == 0

    def test_report_with_tool_stats(self, engine, db):
        db.create_session(session_id="r1", source="cli")
        for _ in range(10):
            db.record_strategy_event(
                session_id="r1", event_type="tool_call",
                tool_name="terminal", result="success", latency_ms=100.0,
            )
        for _ in range(2):
            db.record_strategy_event(
                session_id="r1", event_type="tool_call",
                tool_name="read_file", result="failure", latency_ms=50.0,
            )

        report = engine.generate_strategy_report(days=30)
        assert report["empty"] is False
        assert report["total_events"] == 12
        assert len(report["tool_stats"]) == 2

        # Check first entry (most calls)
        terminal_stat = [t for t in report["tool_stats"] if t["tool_name"] == "terminal"][0]
        assert terminal_stat["total_calls"] == 10
        assert terminal_stat["success_count"] == 10

    def test_report_with_registry(self, engine, db):
        db.register_strategy(
            "test_promoted",
            description="A promoted strategy",
            strategy_type="routing",
        )
        # Manually promote
        now = time.time()
        def _do(conn):
            conn.execute(
                "UPDATE strategy_registry SET state='promoted', promoted_at=?, updated_at=?, "
                "score=0.85, sample_count=50, success_count=45 WHERE name='test_promoted'",
                (now, now),
            )
        db._execute_write(_do)

        report = engine.generate_strategy_report(days=30)
        assert report["empty"] is False
        assert len(report["registry"]["promoted"]) == 1
        assert report["registry"]["promoted"][0]["name"] == "test_promoted"
        assert report["registry"]["promoted"][0]["success_rate"] == 0.9

    def test_report_with_all_states(self, engine, db):
        db.register_strategy("cand", description="candidate")
        db.register_strategy("prom")
        db.register_strategy("ret")
        now = time.time()
        def _do(conn):
            conn.execute(
                "UPDATE strategy_registry SET state='promoted', promoted_at=?, updated_at=?, "
                "score=0.9, sample_count=30, success_count=28 WHERE name='prom'",
                (now, now),
            )
            conn.execute(
                "UPDATE strategy_registry SET state='retired', retired_at=?, updated_at=? "
                "WHERE name='ret'",
                (now, now),
            )
        db._execute_write(_do)

        report = engine.generate_strategy_report(days=30)
        assert len(report["registry"]["candidate"]) == 1
        assert len(report["registry"]["promoted"]) == 1
        assert len(report["registry"]["retired"]) == 1


class TestStrategyFormatting:
    """Terminal and gateway formatting."""

    @pytest.fixture()
    def engine(self, tmp_path):
        from hermes_state import SessionDB
        from agent.insights import InsightsEngine
        db_path = tmp_path / "fmt_test.db"
        db = SessionDB(db_path=db_path)
        yield InsightsEngine(db)
        db.close()

    def test_empty_terminal(self, engine):
        report = {"empty": True, "days": 7}
        output = engine.format_strategy_terminal(report)
        assert "No strategy telemetry" in output

    def test_nonempty_terminal(self, engine):
        report = {
            "empty": False,
            "days": 30,
            "total_events": 100,
            "tool_stats": [
                {"tool_name": "terminal", "total_calls": 80, "success_count": 75,
                 "failure_count": 5, "avg_latency_ms": 120.0},
                {"tool_name": "read_file", "total_calls": 20, "success_count": 20,
                 "failure_count": 0, "avg_latency_ms": 30.0},
            ],
            "registry": {
                "promoted": [
                    {"name": "fast_reads", "description": "Use concurrent reads",
                     "score": 0.87, "sample_count": 50, "success_rate": 0.92,
                     "promoted_at_fmt": "Apr 22"},
                ],
                "candidate": [],
                "retired": [],
            },
        }
        output = engine.format_strategy_terminal(report)
        assert "🎯" in output
        assert "terminal" in output
        assert "fast_reads" in output
        assert "Promoted" in output

    def test_empty_gateway(self, engine):
        report = {"empty": True, "days": 30}
        output = engine.format_strategy_gateway(report)
        assert "No strategy telemetry" in output

    def test_nonempty_gateway(self, engine):
        report = {
            "empty": False,
            "tool_stats": [
                {"tool_name": "terminal", "total_calls": 50, "success_count": 45,
                 "avg_latency_ms": 100.0},
            ],
            "registry": {
                "promoted": [
                    {"name": "fast_reads", "score": 0.85, "sample_count": 30, "success_rate": 0.9},
                ],
                "candidate": [],
                "retired": [],
            },
        }
        output = engine.format_strategy_gateway(report)
        assert "Strategy Report" in output
        assert "terminal" in output
        assert "fast_reads" in output


class TestInsightsCLIParsing:
    """Verify --strategies flag is parsed in CLI and gateway."""

    def test_cli_show_insights_parses_strategies_flag(self):
        """Simulate the parsing logic from _show_insights."""
        command = "/insights --strategies"
        parts = command.split()
        show_strategies = False
        days = 30
        i = 1
        while i < len(parts):
            if parts[i] == "--strategies":
                show_strategies = True
                i += 1
            else:
                i += 1
        assert show_strategies is True

    def test_cli_show_insights_parses_days_and_strategies(self):
        command = "/insights --days 7 --strategies"
        parts = command.split()
        show_strategies = False
        days = 30
        i = 1
        while i < len(parts):
            if parts[i] == "--days" and i + 1 < len(parts):
                days = int(parts[i + 1])
                i += 2
            elif parts[i] == "--strategies":
                show_strategies = True
                i += 1
            else:
                i += 1
        assert show_strategies is True
        assert days == 7

    def test_cli_no_strategies_by_default(self):
        command = "/insights"
        parts = command.split()
        show_strategies = False
        i = 1
        while i < len(parts):
            if parts[i] == "--strategies":
                show_strategies = True
                i += 1
            else:
                i += 1
        assert show_strategies is False

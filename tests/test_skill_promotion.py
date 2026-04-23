"""Tests for skill promotion pipeline (PR 3)."""
import json
import pytest
from pathlib import Path
from tools.skill_manager_tool import skill_manage, _resolve_skill_dir, _get_all_skill_dirs


def _patch_home(tmp_path, monkeypatch):
    """Monkeypatch get_hermes_home and the module-level SKILLS_DIR."""
    monkeypatch.setattr("tools.skill_manager_tool.get_hermes_home", lambda: Path(str(tmp_path)))
    monkeypatch.setattr("tools.skill_manager_tool.SKILLS_DIR", tmp_path / "skills")


class TestPromoteAction:
    def test_promote_nonexistent_skill(self):
        result = json.loads(skill_manage(action="promote", name="nonexistent-skill-xyz"))
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_promote_missing_frontmatter(self, tmp_path, monkeypatch):
        skill_dir = tmp_path / "skills" / "test-no-fm"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("Just some content without frontmatter.")
        _patch_home(tmp_path, monkeypatch)
        result = json.loads(skill_manage(action="promote", name="test-no-fm"))
        assert result["success"] is False
        assert "frontmatter" in result["error"]

    def test_promote_missing_contract(self, tmp_path, monkeypatch):
        skill_dir = tmp_path / "skills" / "test-no-contract"
        skill_dir.mkdir(parents=True)
        content = "---\nname: test-no-contract\ndescription: test\n---\n\nSome body text that is long enough to pass the minimum length check. We need at least two hundred characters total in the body section to pass the gate.\n"
        (skill_dir / "SKILL.md").write_text(content)
        _patch_home(tmp_path, monkeypatch)
        result = json.loads(skill_manage(action="promote", name="test-no-contract"))
        assert result["success"] is False
        assert "Contract" in result["error"]

    def test_promote_stub_skill(self, tmp_path, monkeypatch):
        skill_dir = tmp_path / "skills" / "test-stub"
        skill_dir.mkdir(parents=True)
        content = "---\nname: test-stub\ndescription: test\n---\n\n## Contract\n\nShort.\n"
        (skill_dir / "SKILL.md").write_text(content)
        _patch_home(tmp_path, monkeypatch)
        result = json.loads(skill_manage(action="promote", name="test-stub"))
        assert result["success"] is False
        assert "too short" in result["error"]

    def test_promote_valid_skill(self, tmp_path, monkeypatch):
        skill_dir = tmp_path / "skills" / "test-valid"
        skill_dir.mkdir(parents=True)
        body = "## Contract\n\nThis skill does something useful and has enough content to pass the validation gate. " * 5
        content = f"---\nname: test-valid\ndescription: A valid test skill\n---\n\n{body}\n"
        (skill_dir / "SKILL.md").write_text(content)
        _patch_home(tmp_path, monkeypatch)
        result = json.loads(skill_manage(action="promote", name="test-valid"))
        assert result["success"] is True
        assert "gates_passed" in result
        updated = (skill_dir / "SKILL.md").read_text()
        assert "status: promoted" in updated


class TestGetAllSkillDirs:
    def test_returns_empty_for_no_skills(self, tmp_path, monkeypatch):
        _patch_home(tmp_path, monkeypatch)
        dirs = _get_all_skill_dirs()
        assert dirs == []

    def test_finds_flat_skills(self, tmp_path, monkeypatch):
        skill_dir = tmp_path / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: my-skill\n---\n")
        _patch_home(tmp_path, monkeypatch)
        dirs = _get_all_skill_dirs()
        names = [d.name for d in dirs]
        assert "my-skill" in names

    def test_finds_nested_skills(self, tmp_path, monkeypatch):
        skill_dir = tmp_path / "skills" / "category" / "nested-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: nested-skill\n---\n")
        _patch_home(tmp_path, monkeypatch)
        dirs = _get_all_skill_dirs()
        names = [d.name for d in dirs]
        assert "nested-skill" in names

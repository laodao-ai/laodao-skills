"""
Tests for config_setup.py — Phase 1 Tasks 1-7
Run with: pytest tests/test_config_setup.py -v
"""

import json
import os
import sys
import pytest
from pathlib import Path

# Allow importing config_setup from parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))

import config_setup
from config_setup import (
    read_layer,
    read_three_layers,
    plugin_effective,
    skill_effective,
    discover_plugins,
    parse_skill_description,
    discover_skills,
    backup_and_write,
    merge_and_write_settings,
)


# ============================================================
# Task 1: Three-layer settings file reading
# ============================================================

class TestReadLayer:
    def test_file_exists_with_both_fields(self, tmp_path):
        """File exists with both fields → correct parse"""
        f = tmp_path / "settings.json"
        f.write_text(json.dumps({
            "enabledPlugins": {"firecrawl": True},
            "skillOverrides": {"commit-message": "off"},
        }))
        result = read_layer(f)
        assert result["enabledPlugins"] == {"firecrawl": True}
        assert result["skillOverrides"] == {"commit-message": "off"}

    def test_file_missing_returns_empty_dicts(self, tmp_path):
        """File missing → empty dicts, no error"""
        f = tmp_path / "nonexistent.json"
        result = read_layer(f)
        assert result["enabledPlugins"] == {}
        assert result["skillOverrides"] == {}

    def test_fields_missing_returns_empty_dicts(self, tmp_path):
        """File exists but fields missing → empty dicts"""
        f = tmp_path / "settings.json"
        f.write_text(json.dumps({"theme": "dark"}))
        result = read_layer(f)
        assert result["enabledPlugins"] == {}
        assert result["skillOverrides"] == {}

    def test_malformed_json_exits(self, tmp_path):
        """Malformed JSON → SystemExit"""
        f = tmp_path / "settings.json"
        f.write_text("{not valid json}")
        with pytest.raises(SystemExit):
            read_layer(f)


class TestReadThreeLayers:
    def test_all_three_layers_present(self, tmp_path):
        """All three layers present → correct values"""
        proj = tmp_path / "proj"
        user = tmp_path / "user"
        (proj / ".claude").mkdir(parents=True)
        (user / ".claude").mkdir(parents=True)

        (proj / ".claude" / "settings.local.json").write_text(json.dumps({
            "enabledPlugins": {"firecrawl": True},
            "skillOverrides": {},
        }))
        (proj / ".claude" / "settings.json").write_text(json.dumps({
            "enabledPlugins": {"playwright": False},
            "skillOverrides": {"tag": "off"},
        }))
        (user / ".claude" / "settings.json").write_text(json.dumps({
            "enabledPlugins": {"firecrawl": False},
            "skillOverrides": {"tag": "on"},
        }))

        result = read_three_layers(proj, user)
        assert result["layer3"]["enabledPlugins"] == {"firecrawl": True}
        assert result["layer4"]["enabledPlugins"] == {"playwright": False}
        assert result["layer5"]["skillOverrides"] == {"tag": "on"}

    def test_layer3_missing(self, tmp_path):
        """Layer 3 missing → empty for layer 3"""
        proj = tmp_path / "proj"
        user = tmp_path / "user"
        (proj / ".claude").mkdir(parents=True)
        (user / ".claude").mkdir(parents=True)

        (proj / ".claude" / "settings.json").write_text(json.dumps({
            "enabledPlugins": {"playwright": True},
        }))
        (user / ".claude" / "settings.json").write_text(json.dumps({
            "skillOverrides": {"tag": "off"},
        }))

        result = read_three_layers(proj, user)
        assert result["layer3"]["enabledPlugins"] == {}
        assert result["layer3"]["skillOverrides"] == {}

    def test_all_files_missing(self, tmp_path):
        """All files missing → all empty"""
        proj = tmp_path / "proj"
        user = tmp_path / "user"
        proj.mkdir()
        user.mkdir()

        result = read_three_layers(proj, user)
        for layer in ("layer3", "layer4", "layer5"):
            assert result[layer]["enabledPlugins"] == {}
            assert result[layer]["skillOverrides"] == {}


# ============================================================
# Task 2: enabledPlugins effective state (Solution A' asymmetric)
# ============================================================

class TestPluginEffective:
    def test_local_true_rescues_project_false(self):
        """local True rescues project False → True"""
        assert plugin_effective(True, False, None) is True

    def test_local_false_ignored_when_project_true(self):
        """local False ignored when project True → True"""
        assert plugin_effective(False, True, None) is True

    def test_project_overrides_user(self):
        """project overrides user → project value wins"""
        assert plugin_effective(None, False, True) is False
        assert plugin_effective(None, True, False) is True

    def test_all_none_returns_false(self):
        """all None → False"""
        assert plugin_effective(None, None, None) is False

    def test_user_only(self):
        """user only → user value"""
        assert plugin_effective(None, None, True) is True
        assert plugin_effective(None, None, False) is False

    def test_project_true_only(self):
        """project True only → True"""
        assert plugin_effective(None, True, None) is True

    def test_project_false_only(self):
        """project False only → False"""
        assert plugin_effective(None, False, None) is False

    def test_local_true_overrides_everything(self):
        """local True overrides everything → True"""
        assert plugin_effective(True, False, False) is True
        assert plugin_effective(True, None, None) is True


# ============================================================
# Task 3: skillOverrides effective state (strict symmetric)
# ============================================================

class TestSkillEffective:
    def test_layer3_wins_over_layer4(self):
        """layer3 wins over layer4"""
        assert skill_effective("off", "on", None) == "off"

    def test_layer4_wins_over_layer5(self):
        """layer4 wins over layer5"""
        assert skill_effective(None, "off", "on") == "off"

    def test_layer3_on_beats_layer4_off(self):
        """symmetric/direction: layer3 'on' beats layer4 'off'"""
        assert skill_effective("on", "off", None) == "on"

    def test_all_none_returns_on(self):
        """all None → default 'on'"""
        assert skill_effective(None, None, None) == "on"

    def test_user_invocable_only_propagates(self):
        """user-invocable-only propagates correctly"""
        assert skill_effective(None, "user-invocable-only", None) == "user-invocable-only"

    def test_layer5_only(self):
        """layer5 only → layer5 value"""
        assert skill_effective(None, None, "name-only") == "name-only"


# ============================================================
# Task 4: plugin.json discovery and rich info
# ============================================================

def _make_plugin(cache_dir, org, name, version, plugin_data, subdir=".claude-plugin"):
    """Helper: create plugin.json at the expected path"""
    plugin_dir = cache_dir / org / name / version / subdir
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.json").write_text(json.dumps(plugin_data))


class TestDiscoverPlugins:
    def test_discovers_all_plugins(self, tmp_path):
        """Discovers all plugins"""
        _make_plugin(tmp_path, "org1", "plugA", "1.0.0",
                     {"name": "plugA", "description": "desc A", "homepage": "https://a.com"})
        _make_plugin(tmp_path, "org1", "plugB", "2.0.0",
                     {"name": "plugB", "description": "desc B"})
        result = discover_plugins(tmp_path)
        ids = {p["id"] for p in result}
        assert "plugA@org1" in ids
        assert "plugB@org1" in ids

    def test_full_metadata_extraction(self, tmp_path):
        """Full metadata extraction"""
        _make_plugin(tmp_path, "official", "firecrawl", "1.2.3", {
            "name": "firecrawl",
            "description": "Web scraping plugin",
            "homepage": "https://firecrawl.dev",
            "repository": "https://github.com/firecrawl/firecrawl",
        })
        result = discover_plugins(tmp_path)
        assert len(result) == 1
        p = result[0]
        assert p["id"] == "firecrawl@official"
        assert p["name"] == "firecrawl"
        assert p["description"] == "Web scraping plugin"
        assert p["link"] == "https://firecrawl.dev"
        assert p["homepage"] == "https://firecrawl.dev"
        assert p["repository"] == "https://github.com/firecrawl/firecrawl"

    def test_description_fallback(self, tmp_path):
        """Description missing → '<plugin-id> (no description)'"""
        _make_plugin(tmp_path, "org1", "nod", "1.0.0", {"name": "nod"})
        result = discover_plugins(tmp_path)
        assert len(result) == 1
        assert result[0]["description"] == "nod@org1 (no description)"

    def test_link_priority_repository_fallback(self, tmp_path):
        """Link priority: homepage > repository > None"""
        _make_plugin(tmp_path, "org1", "plugR", "1.0.0", {
            "name": "plugR",
            "repository": "https://github.com/example/plugR",
        })
        result = discover_plugins(tmp_path)
        assert result[0]["link"] == "https://github.com/example/plugR"

    def test_both_links_missing_returns_none(self, tmp_path):
        """Both links missing → None"""
        _make_plugin(tmp_path, "org1", "plugX", "1.0.0", {"name": "plugX"})
        result = discover_plugins(tmp_path)
        assert result[0]["link"] is None

    def test_multi_version_picks_latest(self, tmp_path):
        """Multi-version: pick latest by version number"""
        _make_plugin(tmp_path, "org1", "plug", "1.0.0",
                     {"name": "plug", "description": "old"})
        _make_plugin(tmp_path, "org1", "plug", "2.1.0",
                     {"name": "plug", "description": "new"})
        _make_plugin(tmp_path, "org1", "plug", "1.5.0",
                     {"name": "plug", "description": "middle"})
        result = discover_plugins(tmp_path)
        assert len(result) == 1
        assert result[0]["description"] == "new"

    def test_temp_git_filtered(self, tmp_path):
        """temp_git_ directories at org level are filtered"""
        _make_plugin(tmp_path, "temp_git_abc123", "plug", "1.0.0",
                     {"name": "plug", "description": "should be hidden"})
        _make_plugin(tmp_path, "org1", "plug", "1.0.0",
                     {"name": "plug", "description": "visible"})
        result = discover_plugins(tmp_path)
        assert len(result) == 1
        assert result[0]["description"] == "visible"


# ============================================================
# Task 5: Custom skill discovery + SKILL.md parsing
# ============================================================

class TestParseSkillDescription:
    def test_parse_frontmatter_with_description(self, tmp_path):
        """Parse YAML-style frontmatter with description field"""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("---\nname: test-skill\ndescription: A test skill\n---\n\n# Body")
        result = parse_skill_description(skill_md)
        assert result == "A test skill"

    def test_no_frontmatter_returns_none(self, tmp_path):
        """No frontmatter → None"""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("# Just a heading\n\nBody text.")
        result = parse_skill_description(skill_md)
        assert result is None

    def test_frontmatter_without_description_returns_none(self, tmp_path):
        """Frontmatter without description → None"""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("---\nname: test-skill\nauthor: cheney\n---\n\n# Body")
        result = parse_skill_description(skill_md)
        assert result is None


class TestDiscoverSkills:
    def _make_skill(self, base_dir, skill_name, description=None, nested_in=None):
        """Helper: create a skill directory with SKILL.md"""
        if nested_in:
            skill_dir = base_dir / nested_in / skill_name
        else:
            skill_dir = base_dir / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        if description:
            (skill_dir / "SKILL.md").write_text(
                f"---\nname: {skill_name}\ndescription: {description}\n---\n"
            )
        else:
            (skill_dir / "SKILL.md").write_text(f"---\nname: {skill_name}\n---\n")
        return skill_dir

    def test_discovers_user_level_skills(self, tmp_path):
        """Discovers user-level skills"""
        user_dir = tmp_path / "user"
        proj_dir = tmp_path / "proj"
        plugin_cache = tmp_path / "plugin-cache"
        user_skills = user_dir / ".claude" / "skills"
        self._make_skill(user_skills, "commit-message", "Write commit messages")
        result = discover_skills(proj_dir, user_dir, plugin_cache)
        names = [s["name"] for s in result]
        assert "commit-message" in names

    def test_discovers_project_level_skills(self, tmp_path):
        """Discovers project-level skills"""
        user_dir = tmp_path / "user"
        proj_dir = tmp_path / "proj"
        plugin_cache = tmp_path / "plugin-cache"
        proj_skills = proj_dir / ".claude" / "skills"
        self._make_skill(proj_skills, "my-proj-skill", "Project skill")
        result = discover_skills(proj_dir, user_dir, plugin_cache)
        names = [s["name"] for s in result]
        assert "my-proj-skill" in names

    def test_excludes_without_skill_md(self, tmp_path):
        """Excludes directories without SKILL.md"""
        user_dir = tmp_path / "user"
        proj_dir = tmp_path / "proj"
        plugin_cache = tmp_path / "plugin-cache"
        user_skills = user_dir / ".claude" / "skills"
        # Directory without SKILL.md
        no_skill = user_skills / "no-skill-md"
        no_skill.mkdir(parents=True)
        (no_skill / "script.py").write_text("print('hi')")
        result = discover_skills(proj_dir, user_dir, plugin_cache)
        names = [s["name"] for s in result]
        assert "no-skill-md" not in names

    def test_excludes_plugin_bundled_skills(self, tmp_path):
        """Excludes plugin-bundled skills (under plugin_cache directory)"""
        user_dir = tmp_path / "user"
        proj_dir = tmp_path / "proj"
        plugin_cache = tmp_path / "plugin-cache"
        # Put a "skill" under plugin_cache (should be excluded)
        plugin_skill_dir = plugin_cache / "org1" / "plugA" / "1.0.0" / ".claude-plugin" / "skills" / "plugA-skill"
        plugin_skill_dir.mkdir(parents=True)
        (plugin_skill_dir / "SKILL.md").write_text("---\nname: plugA-skill\ndescription: Plugin skill\n---\n")
        # Also create a user skill that should be included
        user_skills = user_dir / ".claude" / "skills"
        self._make_skill(user_skills, "user-skill", "A real user skill")
        result = discover_skills(proj_dir, user_dir, plugin_cache)
        names = [s["name"] for s in result]
        assert "plugA-skill" not in names
        assert "user-skill" in names

    def test_has_description_and_path(self, tmp_path):
        """Skills have description and path fields"""
        user_dir = tmp_path / "user"
        proj_dir = tmp_path / "proj"
        plugin_cache = tmp_path / "plugin-cache"
        user_skills = user_dir / ".claude" / "skills"
        skill_dir = self._make_skill(user_skills, "my-skill", "My description")
        result = discover_skills(proj_dir, user_dir, plugin_cache)
        skill = next(s for s in result if s["name"] == "my-skill")
        assert skill["description"] == "My description"
        assert Path(skill["path"]) == skill_dir

    def test_level_annotation(self, tmp_path):
        """Level annotation (user vs project)"""
        user_dir = tmp_path / "user"
        proj_dir = tmp_path / "proj"
        plugin_cache = tmp_path / "plugin-cache"
        user_skills = user_dir / ".claude" / "skills"
        proj_skills = proj_dir / ".claude" / "skills"
        self._make_skill(user_skills, "u-skill", "User skill")
        self._make_skill(proj_skills, "p-skill", "Project skill")
        result = discover_skills(proj_dir, user_dir, plugin_cache)
        u = next(s for s in result if s["name"] == "u-skill")
        p = next(s for s in result if s["name"] == "p-skill")
        assert u["level"] == "user"
        assert p["level"] == "project"

    def test_nested_skill_discovery(self, tmp_path):
        """Skills nested 2 levels deep are discovered (e.g. laodao-skills/humanizer-zh/)"""
        user_dir = tmp_path / "user"
        proj_dir = tmp_path / "proj"
        plugin_cache = tmp_path / "plugin-cache"
        user_skills = user_dir / ".claude" / "skills"
        self._make_skill(user_skills, "humanizer-zh", "Humanizer skill", nested_in="laodao-skills")
        result = discover_skills(proj_dir, user_dir, plugin_cache)
        names = [s["name"] for s in result]
        assert "humanizer-zh" in names


# ============================================================
# Task 6: Backup + atomic write
# ============================================================

class TestBackupAndWrite:
    def test_normal_backup_and_write(self, tmp_path):
        """Normal backup and write → backup created, content updated"""
        f = tmp_path / "settings.json"
        f.write_text('{"old": true}')
        backup_and_write(f, '{"new": true}')
        assert f.read_text() == '{"new": true}'
        backups = list(tmp_path.glob("settings.json.bak.*"))
        assert len(backups) == 1

    def test_no_tmp_residue_after_write(self, tmp_path):
        """No .tmp residue after write"""
        f = tmp_path / "settings.json"
        f.write_text('{"old": true}')
        backup_and_write(f, '{"new": true}')
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_no_original_file_skip_backup(self, tmp_path):
        """No original file → skip backup, create new file"""
        f = tmp_path / "settings.json"
        backup_and_write(f, '{"fresh": true}')
        assert f.read_text() == '{"fresh": true}'
        backups = list(tmp_path.glob("*.bak.*"))
        assert len(backups) == 0

    def test_rotation_keeps_exactly_3(self, tmp_path):
        """Rotation keeps exactly 3 (write 5 times → 3 backups remain)"""
        import time
        f = tmp_path / "settings.json"
        f.write_text('{"v": 0}')
        for i in range(1, 6):
            time.sleep(0.01)  # Ensure different mtime
            backup_and_write(f, f'{{"v": {i}}}')
        backups = list(tmp_path.glob("settings.json.bak.*"))
        assert len(backups) == 3

    def test_unchanged_content_no_backup(self, tmp_path):
        """Unchanged content → no backup created"""
        f = tmp_path / "settings.json"
        content = '{"same": true}'
        f.write_text(content)
        backup_and_write(f, content)
        backups = list(tmp_path.glob("*.bak.*"))
        assert len(backups) == 0

    def test_residual_tmp_cleaned(self, tmp_path):
        """Residual .tmp cleaned up before write"""
        f = tmp_path / "settings.json"
        tmp_file = tmp_path / "settings.json.tmp"
        tmp_file.write_text("stale tmp content")
        backup_and_write(f, '{"fresh": true}')
        # After write, no .tmp should remain
        assert not tmp_file.exists()
        assert f.read_text() == '{"fresh": true}'


# ============================================================
# Task 7: Merge-style write boundary protection
# ============================================================

class TestMergeAndWriteSettings:
    def test_merge_enabled_plugins(self, tmp_path):
        """Merge enabledPlugins: existing preserved, new added, changed updated, other fields untouched"""
        f = tmp_path / "settings.json"
        f.write_text(json.dumps({
            "theme": "dark",
            "enabledPlugins": {"firecrawl": False, "playwright": True},
        }, indent=2) + "\n")
        merge_and_write_settings(f, "enabledPlugins", {
            "firecrawl": True,   # change
            "newplugin": True,   # add
        })
        data = json.loads(f.read_text())
        assert data["enabledPlugins"]["firecrawl"] is True     # changed
        assert data["enabledPlugins"]["playwright"] is True    # preserved
        assert data["enabledPlugins"]["newplugin"] is True     # added
        assert data["theme"] == "dark"                         # other field untouched

    def test_merge_skill_overrides(self, tmp_path):
        """Merge skillOverrides: same behavior"""
        f = tmp_path / "settings.json"
        f.write_text(json.dumps({
            "skillOverrides": {"tag": "off", "commit-message": "on"},
        }, indent=2) + "\n")
        merge_and_write_settings(f, "skillOverrides", {
            "tag": "on",
            "humanizer-zh": "name-only",
        })
        data = json.loads(f.read_text())
        assert data["skillOverrides"]["tag"] == "on"
        assert data["skillOverrides"]["commit-message"] == "on"
        assert data["skillOverrides"]["humanizer-zh"] == "name-only"

    def test_unset_removes_key(self, tmp_path):
        """Unset (None) removes key"""
        f = tmp_path / "settings.json"
        f.write_text(json.dumps({
            "enabledPlugins": {"firecrawl": True, "playwright": False},
        }, indent=2) + "\n")
        merge_and_write_settings(f, "enabledPlugins", {"firecrawl": None})
        data = json.loads(f.read_text())
        assert "firecrawl" not in data["enabledPlugins"]
        assert data["enabledPlugins"]["playwright"] is False

    def test_creates_field_if_missing(self, tmp_path):
        """Creates field if missing"""
        f = tmp_path / "settings.json"
        f.write_text(json.dumps({"theme": "dark"}, indent=2) + "\n")
        merge_and_write_settings(f, "enabledPlugins", {"firecrawl": True})
        data = json.loads(f.read_text())
        assert data["enabledPlugins"] == {"firecrawl": True}
        assert data["theme"] == "dark"

    def test_creates_file_if_missing(self, tmp_path):
        """Creates file if missing"""
        f = tmp_path / "settings.json"
        merge_and_write_settings(f, "enabledPlugins", {"firecrawl": True})
        data = json.loads(f.read_text())
        assert data["enabledPlugins"] == {"firecrawl": True}

    def test_sort_keys_output(self, tmp_path):
        """sort_keys output verified"""
        f = tmp_path / "settings.json"
        merge_and_write_settings(f, "enabledPlugins", {
            "zzz-plugin": True,
            "aaa-plugin": True,
        })
        raw = f.read_text()
        data = json.loads(raw)
        # Verify keys are sorted
        keys = list(data["enabledPlugins"].keys())
        assert keys == sorted(keys)
        # Verify ends with newline
        assert raw.endswith("\n")

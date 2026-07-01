"""
Tests for gen_review_stub.py — generates openspec/roadmaps/<name>/review.html.
Run with: python3 -m pytest opsx-roadmap-planner/tests/test_gen_review_stub.py -v
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from gen_review_stub import gen_review_stub


def make_project(tmp_path, with_review_tool=True, with_roadmap_dir=True):
    osroot = tmp_path / "openspec"
    if with_roadmap_dir:
        (osroot / "roadmaps" / "my-feature").mkdir(parents=True)
    if with_review_tool:
        (osroot / "tools").mkdir(parents=True, exist_ok=True)
        (osroot / "tools" / "review-stub.html").write_text(
            '<script>window.__OPENSPEC_REVIEW_SCOPE__ = "__SCOPE__";</script>', encoding="utf-8"
        )
        (osroot / "review.html").write_text("root", encoding="utf-8")
    return tmp_path


class TestGenReviewStub:
    def test_writes_stub_with_correct_scope(self, tmp_path):
        make_project(tmp_path)
        dst = gen_review_stub(str(tmp_path), "my-feature")
        content = Path(dst).read_text(encoding="utf-8")
        assert 'window.__OPENSPEC_REVIEW_SCOPE__ = "roadmaps/my-feature/";' in content

    def test_raises_when_review_tool_missing(self, tmp_path):
        make_project(tmp_path, with_review_tool=False)
        with pytest.raises(FileNotFoundError, match="review 工具"):
            gen_review_stub(str(tmp_path), "my-feature")

    def test_raises_when_roadmap_dir_missing(self, tmp_path):
        make_project(tmp_path, with_roadmap_dir=False)
        with pytest.raises(FileNotFoundError, match="目录不存在"):
            gen_review_stub(str(tmp_path), "my-feature")

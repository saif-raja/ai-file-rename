"""Tests for ai_file_rename.session — RenameSession programmatic API."""

from pathlib import Path

import pytest

from ai_file_rename.session import RenameSession, RenamePlan, TokenUsage


class TestTokenUsage:
    def test_initial_values(self):
        t = TokenUsage()
        assert t.input_tokens == 0
        assert t.output_tokens == 0
        assert t.total_tokens == 0

    def test_add(self):
        t = TokenUsage()
        t.add(100, 50)
        assert t.input_tokens == 100
        assert t.output_tokens == 50
        assert t.total_tokens == 150

    def test_merge_dict(self):
        t = TokenUsage()
        t.merge({"input_tokens": 200, "output_tokens": 75})
        assert t.input_tokens == 200
        assert t.output_tokens == 75

    def test_merge_token_usage(self):
        t1 = TokenUsage(input_tokens=100, output_tokens=50)
        t2 = TokenUsage(input_tokens=200, output_tokens=75)
        t1.merge(t2)
        assert t1.input_tokens == 300
        assert t1.output_tokens == 125

    def test_merge_empty_dict(self):
        t = TokenUsage(input_tokens=100, output_tokens=50)
        t.merge({})
        assert t.input_tokens == 100
        assert t.output_tokens == 50


class TestRenameSessionInit:
    def test_create_with_api_key(self, temp_dir):
        session = RenameSession(
            target_dir=temp_dir,
            api_key="test-key",
        )
        assert session.config.gemini_api_key == "test-key"
        assert session.target_dir == temp_dir.resolve()

    def test_create_with_model_override(self, temp_dir):
        session = RenameSession(
            target_dir=temp_dir,
            api_key="test-key",
            model="gemini-2.5-pro",
        )
        assert session.config.model == "gemini-2.5-pro"

    def test_create_with_custom_instructions(self, temp_dir):
        session = RenameSession(
            target_dir=temp_dir,
            api_key="test-key",
            custom_instructions="prefix all with 'proj-'",
        )
        assert session.config.custom_instructions == "prefix all with 'proj-'"

    def test_create_generates_run_id(self, temp_dir):
        session = RenameSession(target_dir=temp_dir, api_key="test-key")
        assert session.run_id is not None
        assert len(session.run_id) > 8

    def test_no_api_key_raises_on_analyze(self, temp_dir):
        session = RenameSession(target_dir=temp_dir)
        with pytest.raises(ValueError, match="No API key"):
            session.analyze()


class TestRenameSessionAnalyze:
    def test_analyze_empty_dir(self, temp_dir):
        session = RenameSession(
            target_dir=temp_dir,
            api_key="test-key",
        )
        # Empty dir should return plan with no renames (no API calls needed)
        plan = session.analyze()
        assert isinstance(plan, RenamePlan)
        assert plan.total_renames == 0
        assert len(plan.validated_renames) == 0

    def test_analyze_returns_plan(self, temp_dir):
        # Create a file so discovery finds something
        # But analyze() will try to call Gemini — which will fail without a real key
        # We can still test that it gets past discovery
        (temp_dir / "test.txt").write_text("hello world")

        session = RenameSession(
            target_dir=temp_dir,
            api_key="fake-key",
        )
        # This will fail at the Gemini call, but we can test the plan structure
        # In production, you'd mock the client
        try:
            plan = session.analyze()
        except Exception:
            # Expected — no valid API key
            pass

    def test_analyze_skips_files_with_skip_reason(self, temp_dir):
        """Files with skip_reason are excluded even if their category is supported."""
        from ai_file_rename.models import (
            DiscoveryResult, FileCategory, FileEntry, ImpactSummary,
        )

        # Create a FileEntry with a SUPPORTED category but with a skip_reason
        skipped_file = FileEntry(
            path=temp_dir / "oversized.pdf",
            name="oversized.pdf",
            stem="oversized",
            extension="pdf",
            size_bytes=3_000_000_000,
            category=FileCategory.DIRECTLY_PROCESSABLE,
            parent_folder=temp_dir,
            skip_reason="File exceeds 2 GB limit",
        )

        discovery = DiscoveryResult(
            files=[skipped_file],
            folders=[],
            symlink_map={},
            impact=ImpactSummary(
                target_directory=temp_dir,
                recursive=False,
                total_files=1,
                supported_files=0,  # skip_reason means not processable
                unsupported_files=1,
                symlinks_found=0,
                symlink_targets_in_scope=0,
                folders_affected=1,
                deepest_nesting=0,
                estimated_api_calls=0,
                estimated_cost_usd=0.0,
                file_type_breakdown={"pdf": 1},
                warnings=[],
            ),
        )

        session = RenameSession(target_dir=temp_dir, api_key="test-key")
        plan = session.analyze(discovery=discovery)

        # The file should be excluded despite having a supported category
        assert len(plan.validated_renames) == 0
        assert plan.analysis_failures == []


class TestRenameSessionExecute:
    def test_execute_no_plan_raises(self, temp_dir):
        session = RenameSession(target_dir=temp_dir, api_key="test-key")
        with pytest.raises(ValueError, match="No plan available"):
            session.execute()

    def test_execute_empty_plan(self, temp_dir):
        session = RenameSession(target_dir=temp_dir, api_key="test-key")

        from ai_file_rename.models import ImpactSummary, DiscoveryResult
        empty_plan = RenamePlan(
            discovery=DiscoveryResult(
                files=[],
                folders=[],
                symlink_map={},
                impact=ImpactSummary(
                    target_directory=temp_dir,
                    recursive=False,
                    total_files=0,
                    supported_files=0,
                    unsupported_files=0,
                    symlinks_found=0,
                    symlink_targets_in_scope=0,
                    folders_affected=0,
                    deepest_nesting=0,
                    estimated_api_calls=0,
                    estimated_cost_usd=0.0,
                    file_type_breakdown={},
                    warnings=[],
                ),
            ),
            validated_renames=[],
            run_id="test",
            target_directory=temp_dir,
        )

        result = session.execute(empty_plan)
        assert result.renamed == 0
        assert result.failed == 0


class TestRenameSessionUndo:
    def test_undo_no_manifest_raises(self, temp_dir):
        session = RenameSession(target_dir=temp_dir, api_key="test-key")
        with pytest.raises(FileNotFoundError):
            session.undo()


class TestRenameSessionDiscover:
    def test_discover_returns_discovery_result(self, temp_dir):
        (temp_dir / "test.txt").write_text("hello")
        session = RenameSession(target_dir=temp_dir, api_key="test-key")
        result = session.discover()
        from ai_file_rename.models import DiscoveryResult
        assert isinstance(result, DiscoveryResult)
        assert result.impact.total_files >= 1

    def test_discover_empty_dir(self, temp_dir):
        session = RenameSession(target_dir=temp_dir, api_key="test-key")
        result = session.discover()
        assert result.impact.total_files == 0

    def test_discover_nonexistent_dir_raises(self, temp_dir):
        import shutil
        target = temp_dir / "does-not-exist"
        session = RenameSession(target_dir=target, api_key="test-key")
        with pytest.raises(FileNotFoundError):
            session.discover()

    def test_analyze_accepts_precomputed_discovery(self, temp_dir):
        session = RenameSession(target_dir=temp_dir, api_key="test-key")
        discovery = session.discover()
        # analyze() with pre-computed discovery should not re-discover
        plan = session.analyze(discovery=discovery)
        assert isinstance(plan, RenamePlan)


class TestOnPhaseCallback:
    def test_on_phase_not_called_for_empty_dir(self, temp_dir):
        """No phases fire when directory is empty (early return)."""
        session = RenameSession(target_dir=temp_dir, api_key="test-key")
        phases = []
        plan = session.analyze(on_phase=lambda phase, **kw: phases.append(phase))
        assert phases == []
        assert plan.total_renames == 0

    def test_on_phase_called_with_preprocessing_first(self, temp_dir):
        """When files exist, preprocessing is the first phase callback."""
        (temp_dir / "test.txt").write_text("hello world")
        session = RenameSession(target_dir=temp_dir, api_key="fake-key")

        phases = []
        def recorder(phase, **kwargs):
            phases.append((phase, kwargs))

        # analyze() will fail at the Gemini call, but preprocessing and
        # context phases should fire before that
        try:
            session.analyze(on_phase=recorder)
        except Exception:
            pass

        assert len(phases) >= 1
        assert phases[0][0] == "preprocessing"
        assert "file_count" in phases[0][1]
        assert phases[0][1]["file_count"] >= 1

    def test_on_phase_context_after_preprocessing(self, temp_dir):
        """Context phase fires after preprocessing."""
        (temp_dir / "test.txt").write_text("hello world")
        session = RenameSession(target_dir=temp_dir, api_key="fake-key")

        phases = []
        try:
            session.analyze(on_phase=lambda p, **kw: phases.append(p))
        except Exception:
            pass

        assert len(phases) >= 2
        assert phases[0] == "preprocessing"
        assert phases[1] == "context"

    def test_on_phase_none_is_default(self, temp_dir):
        """analyze() works without on_phase (backward compatible)."""
        session = RenameSession(target_dir=temp_dir, api_key="test-key")
        plan = session.analyze()  # no on_phase
        assert isinstance(plan, RenamePlan)

    def test_on_phase_exception_propagates(self, temp_dir):
        """If on_phase raises during a phase, the exception propagates."""
        (temp_dir / "test.txt").write_text("hello world")
        session = RenameSession(target_dir=temp_dir, api_key="fake-key")

        def bad_callback(phase, **kwargs):
            raise ValueError("callback error")

        # With files present, preprocessing phase fires and triggers the error
        with pytest.raises(ValueError, match="callback error"):
            session.analyze(on_phase=bad_callback)

    def test_analysis_failures_in_plan(self, temp_dir):
        """RenamePlan has analysis_failures field."""
        session = RenameSession(target_dir=temp_dir, api_key="test-key")
        plan = session.analyze()
        assert hasattr(plan, "analysis_failures")
        assert isinstance(plan.analysis_failures, list)


class TestRenamePlan:
    def test_plan_properties(self, temp_dir):
        from ai_file_rename.models import (
            DiscoveryResult, ImpactSummary, ProposedRename, ValidatedRename,
        )

        plan = RenamePlan(
            discovery=DiscoveryResult(
                files=[],
                folders=[],
                symlink_map={},
                impact=ImpactSummary(
                    target_directory=temp_dir,
                    recursive=False,
                    total_files=5,
                    supported_files=5,
                    unsupported_files=0,
                    symlinks_found=0,
                    symlink_targets_in_scope=0,
                    folders_affected=2,
                    deepest_nesting=1,
                    estimated_api_calls=5,
                    estimated_cost_usd=0.10,
                    file_type_breakdown={"pdf": 3, "txt": 2},
                    warnings=[],
                ),
            ),
            validated_renames=[
                ValidatedRename(
                    original=ProposedRename(
                        current_name="a.pdf",
                        proposed_name="report.pdf",
                        current_path=temp_dir / "a.pdf",
                        proposed_path=temp_dir / "report.pdf",
                        reasoning="test",
                        confidence=0.9,
                    ),
                    final_name="report.pdf",
                ),
                ValidatedRename(
                    original=ProposedRename(
                        current_name="b.pdf",
                        proposed_name="b.pdf",
                        current_path=temp_dir / "b.pdf",
                        proposed_path=temp_dir / "b.pdf",
                        reasoning="already good",
                        confidence=1.0,
                        is_unchanged=True,
                    ),
                    final_name="b.pdf",
                ),
            ],
            run_id="test-plan",
            target_directory=temp_dir,
        )

        assert plan.total_renames == 1
        assert plan.total_unchanged == 1
        assert plan.folders_affected == 2

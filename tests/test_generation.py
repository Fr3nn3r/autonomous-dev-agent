"""Tests for the generation module (AI-driven feature backlog generation)."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import os

from autonomous_dev_agent.generation import SpecParser, ParsedSpec, FeatureGenerator, GeneratedBacklog
from autonomous_dev_agent.models import Backlog, Feature, FeatureStatus, FeatureCategory


class TestSpecParser:
    """Tests for the SpecParser class."""

    def test_parse_valid_txt_file(self, tmp_path):
        """Test parsing a valid .txt spec file."""
        spec_file = tmp_path / "spec.txt"
        content = """My Application Specification

This is a detailed description of what the application should do.
It should have multiple features including user authentication,
data processing, and reporting capabilities.

The application will serve as a comprehensive solution for managing
user workflows and data analysis tasks.
"""
        spec_file.write_text(content)

        parser = SpecParser(spec_file)
        spec = parser.parse()

        assert spec.file_path == spec_file
        assert spec.content == content
        assert spec.word_count > 0
        assert spec.is_valid

    def test_parse_valid_markdown_file(self, tmp_path):
        """Test parsing a valid .md spec file with sections."""
        spec_file = tmp_path / "spec.md"
        content = """# My Application

This is the application specification.

## Features

- User authentication
- Data processing
- Reporting

## Technical Requirements

The application should be built with Python and use a SQLite database.
It needs to support REST APIs and have a web-based UI.
"""
        spec_file.write_text(content)

        parser = SpecParser(spec_file)
        spec = parser.parse()

        assert spec.file_path == spec_file
        assert spec.title == "My Application"
        assert "Features" in spec.sections
        assert "Technical Requirements" in spec.sections
        assert spec.is_valid

    def test_parse_file_not_found(self, tmp_path):
        """Test error when spec file doesn't exist."""
        spec_file = tmp_path / "nonexistent.txt"

        with pytest.raises(FileNotFoundError) as exc_info:
            SpecParser(spec_file)

        assert "not found" in str(exc_info.value)

    def test_parse_unsupported_extension(self, tmp_path):
        """Test error for unsupported file extension."""
        spec_file = tmp_path / "spec.json"
        spec_file.write_text('{"key": "value"}')

        with pytest.raises(ValueError) as exc_info:
            SpecParser(spec_file)

        assert "Unsupported file extension" in str(exc_info.value)

    def test_parse_file_too_short(self, tmp_path):
        """Test error when spec file is too short."""
        spec_file = tmp_path / "spec.txt"
        spec_file.write_text("Too short")

        parser = SpecParser(spec_file)

        with pytest.raises(ValueError) as exc_info:
            parser.parse()

        assert "too short" in str(exc_info.value)

    def test_validate_path_valid(self, tmp_path):
        """Test path validation for valid spec file."""
        spec_file = tmp_path / "spec.txt"
        spec_file.write_text("A" * 200)  # Long enough content

        is_valid, error = SpecParser.validate_path(spec_file)

        assert is_valid is True
        assert error == ""

    def test_validate_path_not_found(self, tmp_path):
        """Test path validation for missing file."""
        spec_file = tmp_path / "missing.txt"

        is_valid, error = SpecParser.validate_path(spec_file)

        assert is_valid is False
        assert "not found" in error

    def test_validate_path_wrong_extension(self, tmp_path):
        """Test path validation for wrong extension."""
        spec_file = tmp_path / "spec.py"
        spec_file.write_text("# Python code")

        is_valid, error = SpecParser.validate_path(spec_file)

        assert is_valid is False
        assert "Unsupported extension" in error

    def test_truncated_content(self, tmp_path):
        """Test content truncation for very long specs."""
        spec_file = tmp_path / "spec.txt"
        # Create content longer than MAX_CONTENT_LENGTH
        long_content = "A" * 150000
        spec_file.write_text(long_content)

        parser = SpecParser(spec_file)
        spec = parser.parse()

        truncated = spec.get_truncated_content(max_length=1000)
        assert len(truncated) < len(long_content)
        assert "truncated" in truncated.lower()


class TestFeatureGenerator:
    """Tests for the FeatureGenerator class."""

    def test_init_defaults(self):
        """Test generator initializes with default values."""
        generator = FeatureGenerator()

        assert generator.model == "claude-opus-4-20250514"
        assert generator.min_features == 20
        assert generator.max_features == 50

    def test_init_custom_values(self):
        """Test generator initializes with custom values."""
        generator = FeatureGenerator(
            model="claude-opus-4-5-20251101",
            min_features=10,
            max_features=30,
        )

        assert generator.model == "claude-opus-4-5-20251101"
        assert generator.min_features == 10
        assert generator.max_features == 30

    def test_parse_response_valid_json(self):
        """Test parsing a valid JSON response from Claude."""
        generator = FeatureGenerator()

        response = '''```json
[
  {
    "id": "project-setup",
    "name": "Project Setup",
    "description": "Initialize the project structure",
    "category": "infrastructure",
    "priority": 100,
    "acceptance_criteria": ["Package.json created", "Dependencies installed"],
    "steps": ["Run npm init", "Install deps"],
    "depends_on": []
  },
  {
    "id": "user-auth",
    "name": "User Authentication",
    "description": "Implement user login and registration",
    "category": "functional",
    "priority": 85,
    "acceptance_criteria": ["Users can register", "Users can login"],
    "depends_on": ["project-setup"]
  }
]
```'''

        features = generator._parse_response(response)

        assert len(features) == 2
        assert features[0].id == "project-setup"
        assert features[0].name == "Project Setup"
        assert features[0].category == FeatureCategory.INFRASTRUCTURE
        assert features[0].priority == 100
        assert features[0].source == "generated"
        assert len(features[0].acceptance_criteria) == 2
        assert len(features[0].steps) == 2

        assert features[1].id == "user-auth"
        assert features[1].depends_on == ["project-setup"]

    def test_parse_response_raw_json(self):
        """Test parsing raw JSON without markdown code blocks."""
        generator = FeatureGenerator()

        response = '''[
  {
    "id": "feature-1",
    "name": "Feature One",
    "description": "First feature",
    "category": "functional",
    "priority": 50
  }
]'''

        features = generator._parse_response(response)

        assert len(features) == 1
        assert features[0].id == "feature-1"

    def test_parse_response_invalid_json(self):
        """Test handling invalid JSON response."""
        generator = FeatureGenerator()

        response = "This is not valid JSON at all"

        features = generator._parse_response(response)

        assert features == []

    def test_parse_response_empty(self):
        """Test handling empty response."""
        generator = FeatureGenerator()

        features = generator._parse_response("")

        assert features == []

    def test_parse_feature_item_missing_required_fields(self):
        """Test parsing feature with missing required fields."""
        generator = FeatureGenerator()

        # Missing id
        item1 = {"name": "Test", "description": "Test"}
        assert generator._parse_feature_item(item1) is None

        # Missing name
        item2 = {"id": "test", "description": "Test"}
        assert generator._parse_feature_item(item2) is None

    def test_parse_feature_item_category_mapping(self):
        """Test category string to enum mapping."""
        generator = FeatureGenerator()

        test_cases = [
            ("functional", FeatureCategory.FUNCTIONAL),
            ("infrastructure", FeatureCategory.INFRASTRUCTURE),
            ("testing", FeatureCategory.TESTING),
            ("documentation", FeatureCategory.DOCUMENTATION),
            ("bugfix", FeatureCategory.BUGFIX),
            ("refactor", FeatureCategory.REFACTOR),
            ("unknown", FeatureCategory.FUNCTIONAL),  # Default
        ]

        for category_str, expected_enum in test_cases:
            item = {
                "id": f"test-{category_str}",
                "name": "Test Feature",
                "description": "Test",
                "category": category_str,
            }
            feature = generator._parse_feature_item(item)
            assert feature.category == expected_enum

    def test_parse_feature_item_priority_clamping(self):
        """Test priority values are clamped to 0-100."""
        generator = FeatureGenerator()

        # Too high
        item1 = {"id": "test1", "name": "Test", "description": "Test", "priority": 150}
        feature1 = generator._parse_feature_item(item1)
        assert feature1.priority == 100

        # Too low
        item2 = {"id": "test2", "name": "Test", "description": "Test", "priority": -50}
        feature2 = generator._parse_feature_item(item2)
        assert feature2.priority == 0

    @patch.object(FeatureGenerator, '_call_claude')
    def test_generate_success(self, mock_call_claude, tmp_path):
        """Test successful feature generation with mocked Claude call."""
        # Create a spec file
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("""# Test Application

This is a test specification for generating features.
The application should have user management and data processing.
""")

        # Mock Claude response
        mock_response = '''```json
[
  {
    "id": "project-setup",
    "name": "Project Setup",
    "description": "Initialize the project",
    "category": "infrastructure",
    "priority": 100,
    "acceptance_criteria": ["Setup complete"],
    "depends_on": []
  }
]
```'''
        mock_call_claude.return_value = mock_response

        generator = FeatureGenerator(min_features=1, max_features=10)
        result = generator.generate_from_file(
            spec_path=spec_file,
            project_name="Test Project",
            project_path=tmp_path,
        )

        assert isinstance(result, GeneratedBacklog)
        assert result.feature_count == 1
        assert result.backlog.project_name == "Test Project"
        assert result.model_used == "claude-opus-4-20250514"

    @patch.object(FeatureGenerator, '_call_claude')
    def test_generate_cli_error(self, mock_call_claude, tmp_path):
        """Test handling Claude SDK errors."""
        spec_file = tmp_path / "spec.txt"
        spec_file.write_text("A" * 200)

        mock_call_claude.side_effect = RuntimeError("Claude Agent SDK error: rate limit exceeded")

        generator = FeatureGenerator()

        with pytest.raises(RuntimeError) as exc_info:
            generator.generate_from_file(spec_file)

        assert "Claude Agent SDK error" in str(exc_info.value)

    @patch.object(FeatureGenerator, '_call_claude')
    def test_generate_empty_response(self, mock_call_claude, tmp_path):
        """Test handling empty Claude response."""
        spec_file = tmp_path / "spec.txt"
        spec_file.write_text("A" * 200)

        mock_call_claude.return_value = ""

        generator = FeatureGenerator()

        with pytest.raises(RuntimeError) as exc_info:
            generator.generate_from_file(spec_file)

        assert "empty response" in str(exc_info.value)

    def test_merge_with_existing_no_conflicts(self, tmp_path):
        """Test merging generated backlog with existing (no conflicts)."""
        generator = FeatureGenerator()

        existing = Backlog(
            project_name="Test",
            project_path=str(tmp_path),
            features=[
                Feature(id="existing-1", name="Existing 1", description="Test"),
            ]
        )

        generated = GeneratedBacklog(
            backlog=Backlog(
                project_name="Test",
                project_path=str(tmp_path),
                features=[
                    Feature(id="new-1", name="New 1", description="Test", priority=80),
                ]
            ),
            spec_path=tmp_path / "spec.txt",
            model_used="test-model",
        )

        merged = generator.merge_with_existing(generated, existing)

        assert len(merged.features) == 2
        feature_ids = {f.id for f in merged.features}
        assert "existing-1" in feature_ids
        assert "new-1" in feature_ids

    def test_merge_with_existing_with_conflicts(self, tmp_path):
        """Test merging with conflicting feature IDs."""
        generator = FeatureGenerator()

        existing = Backlog(
            project_name="Test",
            project_path=str(tmp_path),
            features=[
                Feature(id="feature-1", name="Original", description="Original desc"),
            ]
        )

        generated = GeneratedBacklog(
            backlog=Backlog(
                project_name="Test",
                project_path=str(tmp_path),
                features=[
                    Feature(id="feature-1", name="Updated", description="Updated desc"),
                    Feature(id="feature-2", name="New", description="New feature"),
                ]
            ),
            spec_path=tmp_path / "spec.txt",
            model_used="test-model",
        )

        # Without prefer_generated - keep original
        merged1 = generator.merge_with_existing(generated, existing, prefer_generated=False)
        assert len(merged1.features) == 2
        assert merged1.features[0].name != "Updated" or merged1.features[1].name != "Updated"

        # With prefer_generated - use new version
        merged2 = generator.merge_with_existing(generated, existing, prefer_generated=True)
        feature_1 = next(f for f in merged2.features if f.id == "feature-1")
        assert feature_1.name == "Updated"


class TestFeatureWithNewFields:
    """Tests for the new Feature fields (steps, source)."""

    def test_feature_with_steps(self):
        """Test creating a feature with steps."""
        feature = Feature(
            id="test-feature",
            name="Test Feature",
            description="Test",
            steps=["Step 1", "Step 2", "Step 3"],
        )

        assert len(feature.steps) == 3
        assert feature.steps[0] == "Step 1"

    def test_feature_with_source(self):
        """Test creating a feature with source tracking."""
        manual = Feature(id="f1", name="F1", description="", source="manual")
        discovery = Feature(id="f2", name="F2", description="", source="discovery")
        generated = Feature(id="f3", name="F3", description="", source="generated")

        assert manual.source == "manual"
        assert discovery.source == "discovery"
        assert generated.source == "generated"

    def test_feature_defaults(self):
        """Test default values for new fields."""
        feature = Feature(id="test", name="Test", description="Test")

        assert feature.steps == []
        assert feature.source is None

    def test_feature_json_serialization(self):
        """Test JSON serialization includes new fields."""
        feature = Feature(
            id="test",
            name="Test",
            description="Test",
            steps=["Step 1"],
            source="generated",
        )

        json_str = feature.model_dump_json()
        data = json.loads(json_str)

        assert "steps" in data
        assert data["steps"] == ["Step 1"]
        assert "source" in data
        assert data["source"] == "generated"

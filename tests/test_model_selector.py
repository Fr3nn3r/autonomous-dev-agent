"""Tests for adaptive model selection."""

import pytest

from autonomous_dev_agent.model_selector import (
    ModelSelector,
    MODELS,
    DEFAULT_MODEL,
    COMPLEX_MODEL,
    SIMPLE_MODEL,
    COMPLEXITY_KEYWORDS,
    SIMPLE_KEYWORDS,
    select_model_for_feature,
    explain_model_selection,
)
from autonomous_dev_agent.models import Feature, FeatureCategory


@pytest.fixture
def selector():
    """Create a ModelSelector instance."""
    return ModelSelector()


@pytest.fixture
def simple_feature():
    """Create a simple feature for testing."""
    return Feature(
        id="fix-typo",
        name="Fix typo in README",
        description="Fix a typo in the documentation",
        category=FeatureCategory.DOCUMENTATION
    )


@pytest.fixture
def complex_feature():
    """Create a complex feature for testing."""
    return Feature(
        id="auth-refactor",
        name="Refactor authentication system",
        description="Redesign the authentication architecture to support OAuth and JWT tokens with improved security",
        category=FeatureCategory.REFACTOR,
        depends_on=["user-model", "session-manager", "token-service"],
        acceptance_criteria=[
            "OAuth2 support",
            "JWT token generation",
            "Token refresh mechanism",
            "Session invalidation",
            "Rate limiting",
            "Audit logging"
        ]
    )


@pytest.fixture
def medium_feature():
    """Create a medium complexity feature for testing."""
    return Feature(
        id="add-button",
        name="Add user profile page",
        description="Add a user profile page that displays user information and allows editing basic settings",
        category=FeatureCategory.FUNCTIONAL,
        depends_on=["user-model"],
        acceptance_criteria=["Profile displays", "Edit works", "Saves correctly"]
    )


class TestModelSelector:
    """Test ModelSelector class."""

    def test_initialization_defaults(self, selector):
        """Test default initialization."""
        assert selector.default_model == DEFAULT_MODEL
        assert selector.complex_model == COMPLEX_MODEL
        assert selector.simple_model == SIMPLE_MODEL

    def test_initialization_custom_models(self):
        """Test custom model initialization."""
        selector = ModelSelector(
            default_model="custom-default",
            complex_model="custom-complex",
            simple_model="custom-simple"
        )
        assert selector.default_model == "custom-default"
        assert selector.complex_model == "custom-complex"
        assert selector.simple_model == "custom-simple"

    def test_select_simple_feature(self, selector, simple_feature):
        """Test selecting model for simple feature."""
        model = selector.select_model(simple_feature)
        # Simple features should use Haiku or default
        assert model in [SIMPLE_MODEL, DEFAULT_MODEL]

    def test_select_complex_feature(self, selector, complex_feature):
        """Test selecting model for complex feature."""
        model = selector.select_model(complex_feature)
        # Complex features should use Opus
        assert model == COMPLEX_MODEL

    def test_select_medium_feature(self, selector, medium_feature):
        """Test selecting model for medium complexity feature."""
        model = selector.select_model(medium_feature)
        # Medium features should use default (Sonnet)
        assert model == DEFAULT_MODEL

    def test_model_override_honored(self, selector, medium_feature):
        """Test that model_override is honored."""
        medium_feature.model_override = "custom-model-override"
        model = selector.select_model(medium_feature)
        assert model == "custom-model-override"

    def test_complexity_keywords_increase_score(self, selector):
        """Test that complexity keywords increase complexity score."""
        # Feature with security keyword
        security_feature = Feature(
            id="sec-1",
            name="Implement security audit",
            description="Add security scanning and vulnerability detection",
            category=FeatureCategory.FUNCTIONAL
        )

        # Feature without keywords
        plain_feature = Feature(
            id="plain-1",
            name="Add a new button",
            description="Add a button to the interface",
            category=FeatureCategory.FUNCTIONAL
        )

        security_score = selector._calculate_complexity_score(security_feature)
        plain_score = selector._calculate_complexity_score(plain_feature)

        assert security_score > plain_score

    def test_simple_keywords_decrease_score(self, selector):
        """Test that simple keywords decrease complexity score."""
        # Feature with typo keyword
        typo_feature = Feature(
            id="typo-1",
            name="Fix typo",
            description="Fix a typo in the code",
            category=FeatureCategory.BUGFIX
        )

        # Feature without simple keywords
        plain_feature = Feature(
            id="plain-1",
            name="Implement feature",
            description="Implement a new feature",
            category=FeatureCategory.BUGFIX
        )

        typo_score = selector._calculate_complexity_score(typo_feature)
        plain_score = selector._calculate_complexity_score(plain_feature)

        assert typo_score < plain_score

    def test_dependencies_increase_score(self, selector):
        """Test that more dependencies increase complexity score."""
        # Feature with many dependencies
        many_deps = Feature(
            id="many-deps",
            name="Feature",
            description="A feature",
            depends_on=["dep-1", "dep-2", "dep-3", "dep-4"]
        )

        # Feature with no dependencies
        no_deps = Feature(
            id="no-deps",
            name="Feature",
            description="A feature",
            depends_on=[]
        )

        many_deps_score = selector._calculate_complexity_score(many_deps)
        no_deps_score = selector._calculate_complexity_score(no_deps)

        assert many_deps_score > no_deps_score

    def test_refactor_category_increases_score(self, selector):
        """Test that refactor category increases complexity score."""
        refactor = Feature(
            id="refactor-1",
            name="Refactor module",
            description="Refactor the module",
            category=FeatureCategory.REFACTOR
        )

        functional = Feature(
            id="func-1",
            name="Add feature",
            description="Add a feature",
            category=FeatureCategory.FUNCTIONAL
        )

        refactor_score = selector._calculate_complexity_score(refactor)
        functional_score = selector._calculate_complexity_score(functional)

        assert refactor_score > functional_score

    def test_documentation_category_decreases_score(self, selector):
        """Test that documentation category decreases complexity score."""
        docs = Feature(
            id="docs-1",
            name="Update docs",
            description="Update the documentation",
            category=FeatureCategory.DOCUMENTATION
        )

        functional = Feature(
            id="func-1",
            name="Add feature",
            description="Add a feature",
            category=FeatureCategory.FUNCTIONAL
        )

        docs_score = selector._calculate_complexity_score(docs)
        functional_score = selector._calculate_complexity_score(functional)

        assert docs_score < functional_score

    def test_many_acceptance_criteria_increases_score(self, selector):
        """Test that many acceptance criteria increase complexity score."""
        many_criteria = Feature(
            id="many-crit",
            name="Feature",
            description="A feature",
            acceptance_criteria=[f"Criterion {i}" for i in range(6)]
        )

        few_criteria = Feature(
            id="few-crit",
            name="Feature",
            description="A feature",
            acceptance_criteria=["Criterion 1"]
        )

        many_score = selector._calculate_complexity_score(many_criteria)
        few_score = selector._calculate_complexity_score(few_criteria)

        assert many_score > few_score

    def test_sessions_spent_increases_score(self, selector):
        """Test that sessions spent increases complexity score (stubborn task)."""
        stubborn = Feature(
            id="stubborn",
            name="Stubborn feature",
            description="A feature that took many sessions",
            sessions_spent=5
        )

        fresh = Feature(
            id="fresh",
            name="Fresh feature",
            description="A new feature",
            sessions_spent=0
        )

        stubborn_score = selector._calculate_complexity_score(stubborn)
        fresh_score = selector._calculate_complexity_score(fresh)

        assert stubborn_score > fresh_score


class TestExplainSelection:
    """Test model selection explanation."""

    def test_explain_includes_model(self, selector, medium_feature):
        """Test explanation includes selected model."""
        explanation = selector.explain_selection(medium_feature)

        assert "model" in explanation
        assert explanation["model"] in [DEFAULT_MODEL, COMPLEX_MODEL, SIMPLE_MODEL]

    def test_explain_includes_score(self, selector, medium_feature):
        """Test explanation includes complexity score."""
        explanation = selector.explain_selection(medium_feature)

        assert "complexity_score" in explanation
        assert isinstance(explanation["complexity_score"], int)

    def test_explain_includes_reasons(self, selector, complex_feature):
        """Test explanation includes reasons."""
        explanation = selector.explain_selection(complex_feature)

        assert "reasons" in explanation
        assert isinstance(explanation["reasons"], list)
        assert len(explanation["reasons"]) > 0

    def test_explain_includes_recommendation(self, selector, medium_feature):
        """Test explanation includes recommendation."""
        explanation = selector.explain_selection(medium_feature)

        assert "recommendation" in explanation
        assert isinstance(explanation["recommendation"], str)

    def test_explain_model_override(self, selector, medium_feature):
        """Test explanation for model override."""
        medium_feature.model_override = "my-custom-model"
        explanation = selector.explain_selection(medium_feature)

        assert explanation["model"] == "my-custom-model"
        assert any("override" in r.lower() for r in explanation["reasons"])

    def test_explain_model_name(self, selector, complex_feature):
        """Test explanation includes human-readable model name."""
        explanation = selector.explain_selection(complex_feature)

        assert "model_name" in explanation
        assert explanation["model_name"] in ["Opus", "Sonnet", "Haiku"]


class TestGetModelInfo:
    """Test model information retrieval."""

    def test_get_opus_info(self, selector):
        """Test getting Opus model info."""
        info = selector.get_model_info(MODELS["opus"])

        assert info["short_name"] == "opus"
        assert "$15/M" in info["input"]
        assert "$75/M" in info["output"]

    def test_get_sonnet_info(self, selector):
        """Test getting Sonnet model info."""
        info = selector.get_model_info(MODELS["sonnet"])

        assert info["short_name"] == "sonnet"
        assert "$3/M" in info["input"]
        assert "$15/M" in info["output"]

    def test_get_haiku_info(self, selector):
        """Test getting Haiku model info."""
        info = selector.get_model_info(MODELS["haiku"])

        assert info["short_name"] == "haiku"
        assert "$1/M" in info["input"]
        assert "$5/M" in info["output"]

    def test_get_unknown_model_info(self, selector):
        """Test getting unknown model info."""
        info = selector.get_model_info("unknown-model-xyz")

        assert info["short_name"] == "unknown"


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_select_model_for_feature(self, medium_feature):
        """Test select_model_for_feature function."""
        model = select_model_for_feature(medium_feature)
        assert model in [DEFAULT_MODEL, COMPLEX_MODEL, SIMPLE_MODEL]

    def test_explain_model_selection(self, medium_feature):
        """Test explain_model_selection function."""
        explanation = explain_model_selection(medium_feature)

        assert "model" in explanation
        assert "complexity_score" in explanation
        assert "reasons" in explanation


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_feature(self, selector):
        """Test selection for minimal feature."""
        minimal = Feature(
            id="minimal",
            name="",
            description=""
        )

        # Should not raise and should return a valid model
        model = selector.select_model(minimal)
        assert model in [DEFAULT_MODEL, COMPLEX_MODEL, SIMPLE_MODEL]

    def test_very_long_description(self, selector):
        """Test that long descriptions are handled."""
        long_desc = Feature(
            id="long",
            name="Feature",
            description="A" * 1000  # Very long description
        )

        model = selector.select_model(long_desc)
        assert model in [DEFAULT_MODEL, COMPLEX_MODEL, SIMPLE_MODEL]

    def test_all_complexity_indicators(self, selector):
        """Test feature with all complexity indicators."""
        max_complex = Feature(
            id="max-complex",
            name="Security architecture refactor",
            description="Redesign the authentication and authorization architecture with OAuth integration",
            category=FeatureCategory.REFACTOR,
            depends_on=["dep-1", "dep-2", "dep-3", "dep-4", "dep-5"],
            acceptance_criteria=[f"Criterion {i}" for i in range(10)],
            sessions_spent=5
        )

        model = selector.select_model(max_complex)
        # With all complexity indicators, should definitely use Opus
        assert model == COMPLEX_MODEL

    def test_all_simplicity_indicators(self, selector):
        """Test feature with all simplicity indicators."""
        max_simple = Feature(
            id="max-simple",
            name="Fix typo",
            description="Fix typo",
            category=FeatureCategory.DOCUMENTATION,
            depends_on=[],
            acceptance_criteria=[],
            sessions_spent=0
        )

        model = selector.select_model(max_simple)
        # With all simplicity indicators, should use Haiku
        assert model == SIMPLE_MODEL

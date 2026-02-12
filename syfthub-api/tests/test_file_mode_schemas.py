"""Tests for file_mode schemas."""

import pytest
from pydantic import ValidationError

from syfthub_api.file_mode.schemas import EndpointConfig, PolicyConfig


class TestEndpointConfig:
    """Tests for EndpointConfig validation."""

    def test_valid_model_endpoint(self) -> None:
        """Test valid model endpoint configuration."""
        config = EndpointConfig(
            slug="my-model",
            type="model",
            name="My Model",
            description="A test model",
        )
        assert config.slug == "my-model"
        assert config.type == "model"
        assert config.name == "My Model"
        assert config.description == "A test model"
        assert config.enabled is True  # default

    def test_valid_datasource_endpoint(self) -> None:
        """Test valid data source endpoint configuration."""
        config = EndpointConfig(
            slug="my-data",
            type="data_source",
            name="My Data",
            description="A test data source",
        )
        assert config.type == "data_source"

    def test_slug_validation_empty(self) -> None:
        """Test that empty slug is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EndpointConfig(
                slug="",
                type="model",
                name="Test",
                description="Test",
            )
        assert "slug cannot be empty" in str(exc_info.value).lower()

    def test_slug_validation_invalid_characters(self) -> None:
        """Test that invalid slug characters are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EndpointConfig(
                slug="My Model",  # uppercase and space
                type="model",
                name="Test",
                description="Test",
            )
        assert "invalid slug" in str(exc_info.value).lower()

    def test_slug_validation_too_long(self) -> None:
        """Test that overly long slugs are rejected."""
        with pytest.raises(ValidationError):
            EndpointConfig(
                slug="a" * 100,  # too long
                type="model",
                name="Test",
                description="Test",
            )

    def test_name_validation_empty(self) -> None:
        """Test that empty name is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EndpointConfig(
                slug="test",
                type="model",
                name="",
                description="Test",
            )
        assert "name cannot be empty" in str(exc_info.value).lower()

    def test_name_validation_whitespace_only(self) -> None:
        """Test that whitespace-only name is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EndpointConfig(
                slug="test",
                type="model",
                name="   ",
                description="Test",
            )
        assert "name cannot be empty" in str(exc_info.value).lower()

    def test_description_optional(self) -> None:
        """Test that description can be empty."""
        config = EndpointConfig(
            slug="test",
            type="model",
            name="Test",
            description="",
        )
        assert config.description == ""

    def test_enabled_default_true(self) -> None:
        """Test that enabled defaults to True."""
        config = EndpointConfig(
            slug="test",
            type="model",
            name="Test",
            description="Test",
        )
        assert config.enabled is True

    def test_enabled_can_be_false(self) -> None:
        """Test that enabled can be set to False."""
        config = EndpointConfig(
            slug="test",
            type="model",
            name="Test",
            description="Test",
            enabled=False,
        )
        assert config.enabled is False

    def test_invalid_type(self) -> None:
        """Test that invalid endpoint type is rejected."""
        with pytest.raises(ValidationError):
            EndpointConfig(
                slug="test",
                type="invalid",  # type: ignore
                name="Test",
                description="Test",
            )


class TestPolicyConfig:
    """Tests for PolicyConfig validation."""

    def test_simple_policy(self) -> None:
        """Test simple policy configuration."""
        config = PolicyConfig(
            type="RateLimitPolicy",
            config={"max_requests": 100, "window_seconds": 60},
        )
        assert config.type == "RateLimitPolicy"
        assert config.config["max_requests"] == 100
        assert config.name is None  # optional

    def test_policy_with_name(self) -> None:
        """Test policy with explicit name."""
        config = PolicyConfig(
            type="RateLimitPolicy",
            name="my_rate_limit",
            config={"max_requests": 100},
        )
        assert config.name == "my_rate_limit"

    def test_composite_policy(self) -> None:
        """Test composite policy with nested policies."""
        config = PolicyConfig(
            type="AllOf",
            name="combined",
            policies=[
                PolicyConfig(type="RateLimitPolicy", config={"max_requests": 100}),
                PolicyConfig(type="TokenLimitPolicy", config={"max_input_tokens": 500}),
            ],
        )
        assert config.type == "AllOf"
        assert len(config.policies) == 2
        assert config.policies[0].type == "RateLimitPolicy"
        assert config.policies[1].type == "TokenLimitPolicy"

    def test_empty_type_rejected(self) -> None:
        """Test that empty policy type is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PolicyConfig(type="")
        assert "cannot be empty" in str(exc_info.value).lower()

    def test_empty_config_default(self) -> None:
        """Test that config defaults to empty dict."""
        config = PolicyConfig(type="ManualReviewPolicy")
        assert config.config == {}

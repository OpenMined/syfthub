"""Tests for file_mode policy loader."""

import pytest
from pathlib import Path
import tempfile

from syfthub_api.file_mode.policy_loader import PolicyFactory, PolicyLoadError
from syfthub_api.file_mode.schemas import PolicyConfig


class TestPolicyFactory:
    """Tests for PolicyFactory."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.factory = PolicyFactory()

    def test_get_registered_types(self) -> None:
        """Test getting list of registered policy types."""
        types = self.factory.get_registered_types()
        assert "RateLimitPolicy" in types
        assert "TokenLimitPolicy" in types
        assert "AccessGroupPolicy" in types
        assert "AllOf" in types
        assert "AnyOf" in types

    def test_create_rate_limit_policy(self) -> None:
        """Test creating a RateLimitPolicy."""
        config = PolicyConfig(
            type="RateLimitPolicy",
            name="test_rate_limit",
            config={"max_requests": 100, "window_seconds": 60},
        )
        policy = self.factory.create(config)
        assert policy.name == "test_rate_limit"

    def test_create_token_limit_policy(self) -> None:
        """Test creating a TokenLimitPolicy."""
        config = PolicyConfig(
            type="TokenLimitPolicy",
            config={"max_input_tokens": 500, "max_output_tokens": 1000},
        )
        policy = self.factory.create(config)
        assert policy is not None

    def test_create_access_group_policy(self) -> None:
        """Test creating an AccessGroupPolicy."""
        config = PolicyConfig(
            type="AccessGroupPolicy",
            config={"users": ["alice", "bob"]},
        )
        policy = self.factory.create(config)
        assert policy is not None

    def test_create_unknown_policy_type(self) -> None:
        """Test that unknown policy type raises error."""
        config = PolicyConfig(type="UnknownPolicy", config={})
        with pytest.raises(PolicyLoadError) as exc_info:
            self.factory.create(config)
        assert "unknown policy type" in str(exc_info.value).lower()

    def test_create_composite_allof(self) -> None:
        """Test creating an AllOf composite policy."""
        config = PolicyConfig(
            type="AllOf",
            name="combined",
            policies=[
                PolicyConfig(type="RateLimitPolicy", config={"max_requests": 100, "window_seconds": 60}),
                PolicyConfig(type="TokenLimitPolicy", config={"max_input_tokens": 500}),
            ],
        )
        policy = self.factory.create(config)
        assert policy.name == "combined"

    def test_create_composite_anyof(self) -> None:
        """Test creating an AnyOf composite policy."""
        config = PolicyConfig(
            type="AnyOf",
            name="either",
            policies=[
                PolicyConfig(type="AccessGroupPolicy", config={"users": ["admin"]}),
                PolicyConfig(type="AccessGroupPolicy", config={"users": ["moderator"]}),
            ],
        )
        policy = self.factory.create(config)
        assert policy.name == "either"

    def test_create_not_policy(self) -> None:
        """Test creating a Not composite policy."""
        config = PolicyConfig(
            type="Not",
            name="not_guest",
            policies=[
                PolicyConfig(type="AccessGroupPolicy", config={"users": ["guest"]}),
            ],
        )
        policy = self.factory.create(config)
        assert policy.name == "not_guest"

    def test_create_not_requires_single_policy(self) -> None:
        """Test that Not policy requires exactly one child."""
        config = PolicyConfig(
            type="Not",
            policies=[
                PolicyConfig(type="AccessGroupPolicy", config={"users": ["a"]}),
                PolicyConfig(type="AccessGroupPolicy", config={"users": ["b"]}),
            ],
        )
        with pytest.raises(PolicyLoadError) as exc_info:
            self.factory.create(config)
        assert "exactly one" in str(exc_info.value).lower()

    def test_load_from_yaml(self) -> None:
        """Test loading policy from YAML string."""
        yaml_content = """
type: RateLimitPolicy
name: yaml_rate_limit
config:
  max_requests: 50
  window_seconds: 30
"""
        policy = self.factory.load_from_yaml(yaml_content)
        assert policy.name == "yaml_rate_limit"

    def test_load_from_yaml_invalid(self) -> None:
        """Test that invalid YAML raises error."""
        yaml_content = "not: valid: yaml: content:"
        with pytest.raises(PolicyLoadError):
            self.factory.load_from_yaml(yaml_content)

    def test_load_from_file(self) -> None:
        """Test loading policy from YAML file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("""
type: TokenLimitPolicy
name: file_token_limit
config:
  max_input_tokens: 1000
""")
            f.flush()

            policy = self.factory.load_from_file(Path(f.name))
            assert policy.name == "file_token_limit"

    def test_load_from_nonexistent_file(self) -> None:
        """Test that loading from nonexistent file raises error."""
        with pytest.raises(PolicyLoadError) as exc_info:
            self.factory.load_from_file(Path("/nonexistent/policy.yaml"))
        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_load_policies_from_folder(self) -> None:
        """Test loading multiple policies from a folder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            policy_dir = Path(tmpdir)

            # Create policy files
            (policy_dir / "rate_limit.yaml").write_text("""
type: RateLimitPolicy
name: rate1
config:
  max_requests: 100
  window_seconds: 60
""")
            (policy_dir / "token_limit.yaml").write_text("""
type: TokenLimitPolicy
name: tokens1
config:
  max_input_tokens: 500
""")

            policies = await self.factory.load_policies_from_folder(policy_dir)
            assert len(policies) == 2
            names = {p.name for p in policies}
            assert "rate1" in names
            assert "tokens1" in names

    @pytest.mark.asyncio
    async def test_load_policies_from_empty_folder(self) -> None:
        """Test loading from empty folder returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            policies = await self.factory.load_policies_from_folder(Path(tmpdir))
            assert policies == []

    @pytest.mark.asyncio
    async def test_load_policies_from_nonexistent_folder(self) -> None:
        """Test loading from nonexistent folder returns empty list."""
        policies = await self.factory.load_policies_from_folder(
            Path("/nonexistent/folder")
        )
        assert policies == []

    @pytest.mark.asyncio
    async def test_load_policies_skips_invalid(self) -> None:
        """Test that invalid policy files are skipped, not raised."""
        with tempfile.TemporaryDirectory() as tmpdir:
            policy_dir = Path(tmpdir)

            # Create one valid and one invalid
            (policy_dir / "valid.yaml").write_text("""
type: RateLimitPolicy
name: valid
config:
  max_requests: 100
  window_seconds: 60
""")
            (policy_dir / "invalid.yaml").write_text("""
type: NonexistentPolicy
config: {}
""")

            # Should load the valid one and skip the invalid
            policies = await self.factory.load_policies_from_folder(policy_dir)
            assert len(policies) == 1
            assert policies[0].name == "valid"

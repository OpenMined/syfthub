"""Tests for filter_visible_policies."""

from syfthub.schemas.endpoint import Policy, filter_visible_policies


def _xendit_policy(applied_to=None, description="p"):
    config = {"price_per_request": 1.0}
    if applied_to is not None:
        config["applied_to"] = applied_to
    return Policy(type="xendit", description=description, config=config)


class TestFilterVisiblePolicies:
    def test_missing_applied_to_visible_to_everyone(self):
        p = _xendit_policy(applied_to=None)
        assert filter_visible_policies([p], "user@example.com") == [p]
        assert filter_visible_policies([p], None) == [p]

    def test_empty_applied_to_visible_to_everyone(self):
        p = _xendit_policy(applied_to=[])
        assert filter_visible_policies([p], "user@example.com") == [p]
        assert filter_visible_policies([p], None) == [p]

    def test_wildcard_visible_to_everyone(self):
        p = _xendit_policy(applied_to=["*"])
        assert filter_visible_policies([p], "user@example.com") == [p]
        assert filter_visible_policies([p], None) == [p]

    def test_email_match_visible(self):
        p = _xendit_policy(applied_to=["alice@example.com", "bob@example.com"])
        assert filter_visible_policies([p], "alice@example.com") == [p]

    def test_email_match_is_case_insensitive(self):
        p = _xendit_policy(applied_to=["Alice@Example.com"])
        assert filter_visible_policies([p], "ALICE@example.COM") == [p]

    def test_no_match_filtered_out(self):
        p = _xendit_policy(applied_to=["alice@example.com"])
        assert filter_visible_policies([p], "carol@example.com") == []

    def test_anonymous_viewer_filters_personalized(self):
        p = _xendit_policy(applied_to=["alice@example.com"])
        assert filter_visible_policies([p], None) == []

    def test_targeted_policy_overrides_wildcard_for_listed_user(self):
        wildcard = _xendit_policy(applied_to=["*"], description="all")
        targeted = _xendit_policy(applied_to=["alice@example.com"], description="alice")
        other = _xendit_policy(applied_to=["bob@example.com"], description="bob")
        result = filter_visible_policies(
            [wildcard, targeted, other], "alice@example.com"
        )
        assert result == [targeted]

    def test_unlisted_user_falls_back_to_wildcard(self):
        wildcard = _xendit_policy(applied_to=["*"], description="all")
        targeted = _xendit_policy(applied_to=["alice@example.com"], description="alice")
        other = _xendit_policy(applied_to=["bob@example.com"], description="bob")
        result = filter_visible_policies(
            [wildcard, targeted, other], "carol@example.com"
        )
        assert result == [wildcard]

    def test_unset_applied_to_acts_as_wildcard_fallback(self):
        unset = _xendit_policy(applied_to=None, description="default")
        targeted = _xendit_policy(applied_to=["alice@example.com"], description="alice")
        result_alice = filter_visible_policies([unset, targeted], "alice@example.com")
        assert result_alice == [targeted]
        result_carol = filter_visible_policies([unset, targeted], "carol@example.com")
        assert result_carol == [unset]

    def test_accepts_dict_policies(self):
        wildcard = {"type": "xendit", "config": {"applied_to": ["*"]}}
        targeted = {
            "type": "xendit",
            "config": {"applied_to": ["alice@example.com"]},
        }
        other = {
            "type": "xendit",
            "config": {"applied_to": ["bob@example.com"]},
        }
        result = filter_visible_policies(
            [wildcard, targeted, other], "alice@example.com"
        )
        assert result == [targeted]

    def test_non_string_applied_to_entries_ignored(self):
        p = _xendit_policy(applied_to=[None, 42, "alice@example.com"])
        assert filter_visible_policies([p], "alice@example.com") == [p]
        assert filter_visible_policies([p], "bob@example.com") == []

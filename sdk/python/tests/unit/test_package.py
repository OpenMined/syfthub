import syfthub


def test_version_and_public_surface() -> None:
    assert syfthub.__version__ == "2.0.0a1"
    assert {"SearchPlan", "Results", "Source", "Wallet", "SyftHubError"} <= set(syfthub.__all__)

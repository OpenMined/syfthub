"""Policy enforcement integration for container runner."""
import logging

logger = logging.getLogger("container_runner.policy")


def check_policies(executor_input: dict):
    """Run policy checks if policies are configured.

    Returns policy result dict or None if no policies.
    """
    policies = executor_input.get("policies", [])
    if not policies:
        return None

    try:
        from policy_manager.runner import evaluate_policies

        result = evaluate_policies(
            policies=policies,
            store_config=executor_input.get("store"),
            context=executor_input.get("context", {}),
            handler_input={
                "type": executor_input.get("type"),
                "messages": executor_input.get("messages"),
                "query": executor_input.get("query"),
            },
            transaction_token=executor_input.get("transaction_token"),
        )

        return {
            "allowed": result.get("allowed", True),
            "policy_name": result.get("policy_name", ""),
            "reason": result.get("reason", ""),
            "pending": result.get("pending", False),
            "metadata": result.get("metadata", {}),
        }
    except ImportError:
        logger.warning(
            "policy_manager not installed, skipping policy enforcement"
        )
        return {
            "allowed": True,
            "policy_name": "",
            "reason": "policy_manager not available",
        }
    except Exception as e:
        logger.error("Policy evaluation failed: %s", e)
        return {"allowed": False, "policy_name": "error", "reason": str(e)}

# Security review

Before changing auth, secrets, or security controls:

1. Identify auth and secret touchpoints.
2. Check for credential leakage.
3. Review authorization changes.
4. Confirm tests cover the security path.

Then retry the original action so the guardrail can re-evaluate it.

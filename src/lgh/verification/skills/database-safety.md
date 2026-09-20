# Database safety

Before mutating a database:

1. Identify the target environment.
2. Inspect the generated migration.
3. Perform a dry-run when available.
4. Establish a rollback strategy.

Then retry the original action so the guardrail can re-evaluate it.

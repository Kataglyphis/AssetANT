# Changelog

## Unreleased

- Keep the copied Renovate bootstrap within the strict complexity limit used by CI.
- Use the shared Windows Git selector when a WSL Renovate apply bootstraps the pinned hub;
  sync its exact copied helper alongside the bootstrap.
- Bootstrap a missing pinned ANTfrastructure checkout during a real Renovate apply and update
  direct submodules to their remote default tips; reports and previews do not clone.
- Add the shared Renovate configuration and one-command local dependency update wrapper.
- Add shared size, complexity, duplication and Ruff/ty reports in CI, plus a manual Python
  refactor preview. Generated local reports stay in ignored `logs/`.

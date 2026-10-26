# Changelog

## Unreleased

- Share asset-spec lookup across fetch, pack and release, test its path and missing-file contract
  with a mutation, and make the shared duplication gate fatal with no exceptions.
- Add agent rules that require repository and ANTfrastructure reuse before writing Bash or
  PowerShell helpers and preserve the asset release contract.
- Reuse ANTfrastructure's Python interpreter probe in the image check and let the shared lint
  workflow grade every tracked shell script on every push and pull request.
- Search both script directories when ShellCheck follows the shared Renovate bootstrap companion.
- Keep the copied Renovate bootstrap within strict complexity and trailing-return limits in CI.
- Use the shared Windows Git selector when a WSL Renovate apply bootstraps the pinned hub;
  sync its exact copied helper alongside the bootstrap.
- Bootstrap a missing pinned ANTfrastructure checkout during a real Renovate apply and update
  direct submodules to their remote default tips; reports and previews do not clone.
- Add the shared Renovate configuration and one-command local dependency update wrapper.
- Add shared size, complexity, duplication and Ruff/ty reports in CI, plus a manual Python
  refactor preview. Generated local reports stay in ignored `logs/`.

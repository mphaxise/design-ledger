# Codex installation

## Claim

Design Ledger installs once as a local Codex plugin. Durable repositories then need one project-specific onboarding pass before background verification can be trusted.

## Installed components

- The `design-ledger` plugin provides implicit activation guidance and an asynchronous `PostToolUse` hook.
- The runtime lives in the user's Codex data directory under `design-ledger/bin/`.
- Project events, experience history, receipts, logs, and locks live under `design-ledger/state/`.
- A personal local marketplace exposes the plugin to Codex.

The installed plugin follows the supported local marketplace and plugin-hook surfaces described in the [official OpenAI plugin documentation](https://developers.openai.com/plugins/build/plugins) and [Codex hooks documentation](https://developers.openai.com/codex/hooks).

Codex requires the user to review and trust a plugin hook before it runs. Installation alone does not bypass that trust gate.

## First use in a repository

Codex classifies the task using the durable-development boundary. For a durable repository without an adapter, Codex performs one-time onboarding inside the development task:

1. Read repository instructions and verify Git state.
2. Inventory existing checks and release gates.
3. Add the smallest accurate `.design-ledger/adapter.json`.
4. Run and review one baseline receipt.
5. Enable checkpoint enforcement only after the baseline is trustworthy.

The background hook observes repositories that already have an adapter. It ignores repositories without one.

## Ongoing behavior

After onboarding, the user continues working in normal Codex tasks. Explicit design feedback becomes experience events. New commits are observed and verified asynchronously. Delivery checkpoints read current receipts.

Plugin installation does not grant permission to push, open pull requests, merge, deploy, upload builds, release, or answer human gates.

## Update behavior

Existing local installations synchronize and verify the modular runtime and plugin source with one command:

```sh
python3 scripts/sync_codex_install.py sync --install
```

The plugin manifest carries the release version used as the Codex cache key. A new Codex task loads an updated skill and hook. Existing events and receipts remain in the stable Design Ledger state directory.

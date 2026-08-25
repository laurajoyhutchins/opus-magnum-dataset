# Opportunistic Cleanup

This file records small, understood maintenance improvements that are worth remembering but do not merit independent scheduling.

Pick up an item when modifying the surrounding code and doing so does not materially expand the change. Remove the item in the same pull request that completes it.

Promote an item to a GitHub issue when it requires independent scheduling, architectural or product judgment, cross-module coordination, migration work, or substantial dedicated testing. Do not mirror these items into `docs/TODO.md` or an external project tracker.

Keep this list short. It is not a backlog, dependency graph, or second issue tracker.

## Items

- `src/opus_corpus/release_configs.py`: simplify the derived lookup structures when this module is next touched; keep one authoritative release-config definition and only the indexes actually needed by consumers.

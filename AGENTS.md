# BMK AI Studio development

- For a new maintenance or improvement session, read docs/HANDOFF.md, verify the current Git state, and follow the user's requested scope for that session.
- Default to main for small sequential maintenance tasks. Use a temporary codex/ branch for large changes, experiments, or concurrent work; concurrent sessions require separate worktrees. Clean up completed branches after verifying their commits are in main and origin/main and no active PR or worktree needs them. Preserve unmerged checkpoints with a verified remote archive tag before deleting their branches.
- At the end of each maintenance task, recommend commit, push, and EXE release timing separately, with a brief reason, following the cadence in docs/HANDOFF.md. These recommendations do not authorize execution; honor any explicit authorization already given by the user without asking again.
- This is a standalone Windows app. Never import ComfyUI server, folder_paths or node loader in application code.
- Vendor snapshots are isolated; their optional imports must remain optional.
- Keep original metadata, inferred tags, and work prompts separate. Never fabricate a missing source prompt.
- Never overwrite source images on editing/export. Preserve unknown note fields.
- User data belongs under LOCALAPPDATA/BMK-AI-Studio (or BMK_STUDIO_DATA), never in tracked source.
- Keep UI responsive for model inference and image processing. Guard results against image selection changes.
- Before delivery, run unittest and Qt smoke tests; when tagging changes, also run the optional local-model GPU smoke test.
- Do not upload data, models, notes, caches, or local-settings.json to GitHub.
- Current scope and remaining functionality are documented in README.md. Do not describe deferred features as implemented.

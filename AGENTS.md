# BMK AI Studio development

- This is a standalone Windows app. Never import ComfyUI server, folder_paths or node loader in application code.
- Vendor snapshots are isolated; their optional imports must remain optional.
- Keep original metadata, inferred tags, and work prompts separate. Never fabricate a missing source prompt.
- Never overwrite source images on editing/export. Preserve unknown note fields.
- User data belongs under LOCALAPPDATA/BMK-AI-Studio (or BMK_STUDIO_DATA), never in tracked source.
- Keep UI responsive for model inference and image processing. Guard results against image selection changes.
- Before delivery, run unittest and Qt smoke tests; when tagging changes, also run the optional local-model GPU smoke test.
- Do not upload data, models, notes, caches, or local-settings.json to GitHub.
- Current scope and remaining functionality are documented in README.md. Do not describe deferred features as implemented.

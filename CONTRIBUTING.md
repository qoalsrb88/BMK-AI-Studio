# Contributing

Use Windows x64 and Python 3.12. Follow README setup instructions and AGENTS.md.

- Keep original metadata, inferred tags and editable prompts separate.
- Preserve original images, existing note fields and user data.
- Do image processing/inference off the UI thread and reject stale results.
- Create a branch for changes. Explain the user-visible problem, resulting behavior and relevant validation in the pull request.
- Run `python scripts/check_repository.py` and `python scripts/validate.py` before submitting. Tagging changes also require the optional local-model GPU test described in docs/DEVELOPMENT.md.
- Use synthetic fixtures. Do not attach private prompts, original images, credentials, local settings, model weights or full user databases to issues or pull requests.

GitHub-hosted Windows CI uses CPU dependencies and no private models. It does not replace local GPU or packaged executable verification.

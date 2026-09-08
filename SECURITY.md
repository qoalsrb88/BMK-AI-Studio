# Security

Do not put credentials, private image metadata, models or user databases in public issues. Reproduce with synthetic data where possible.

For a suspected vulnerability, use the repository Security tab's private vulnerability reporting if enabled. If it is unavailable, ask the maintainer for a private reporting channel without publishing exploit details or private data. No dedicated security contact or response SLA is currently established.

This is a local beta. Images, metadata, imported note JSON and model files should be treated as untrusted inputs. The application must not execute workflow code or silently upload user content. Model installation downloads files; local inference does not upload prompts or images.

# Third-party notices

Application code: [MIT](LICENSE), copyright 2026 qoalsrb88.

## Vendored BMK code

The isolated snapshots in `bmk_studio/vendor/` originate from the BMK custom-node project. Its MIT notice is retained in [BMK_LICENSE.txt](bmk_studio/vendor/BMK_LICENSE.txt), copyright 2026 qoalsrb88. These modules cover metadata extraction, prompt conversion and tag manipulation. Standalone adaptations may differ from the original project; optional imports remain optional.

## Dependencies and distributions

Dependencies are installed separately and retain their own licenses. `build_windows.py` collects installed distribution notices into `_internal/third_party_licenses` for a binary build. The 0.9.8 package also includes the notices in [docs/licenses](docs/licenses) and [exact source/relinking information](docs/DEPENDENCY_SOURCES.md). Qt/PySide6 is used under LGPLv3; NVIDIA CUDA/cuDNN components have separate proprietary terms. That inventory is not a complete compliance review: check the actual Qt/LGPL components, Python, torch/CUDA, codecs and other redistribution requirements before a public binary release. Preserve required notices and provide any required source information for that exact build.

Model weights are not included. WD and multilingual text models retain their own model-card terms. Do not bundle private images, notes or third-party artwork with source releases.

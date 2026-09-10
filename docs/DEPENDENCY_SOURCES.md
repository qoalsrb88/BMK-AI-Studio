# Dependency sources for the Windows 0.9.8 package

The package uses unmodified PySide6 / Shiboken6 / Qt 6.11.2 from the official Python wheels. Qt and the bindings are dynamically loaded, under LGPLv3. The source commit of BMK AI Studio and runtime versions are in build-info.json beside the executable.

## Corresponding Qt and binding sources

The same GitHub v0.9.8 Release provides these source archives beside the executable package. They are optional for running the app, and contain source/build instructions for modifying the libraries. Exact upstream copies and SHA256:

| Archive | SHA256 | Official source |
| --- | --- | --- |
| qt-everywhere-src-6.11.2.tar.xz | 6dcfbca271d76a6502741a2c0dc6fc98ef7dd0b7b4cfd0abcebb285a86a26f33 | https://download.qt.io/archive/qt/6.11/6.11.2/single/qt-everywhere-src-6.11.2.tar.xz |
| pyside-setup-everywhere-src-6.11.2.tar.xz | cba47efbaad1bedd529725cbc14e21f156c7a19366f07b3edfbb076ffd7afdf8 | https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/pyside-setup-everywhere-src-6.11.2.tar.xz |

Included Qt modules come from qtbase, qtsvg and qtimageformats. The full Qt source archive also contains other modules; their presence in that source archive does not mean they are linked into this application. The build excludes Qt Virtual Keyboard and the unused Qt PDF image plugin. Qt notices and LGPL/GPL license copies are in licenses/; Qt's third-party notices include upstream attribution records for the selected source modules.

To modify/relink: retain a backup, build a compatible Windows x64 release of Qt/PySide6 6.11.2 using the instructions in these sources, close the application, and replace corresponding dynamic libraries in _internal/PySide6 and _internal/shiboken6. Preserve the directory layout and binary interface. Alternatively, install your compatible wheels in a separate Python 3.12 environment and rebuild BMK AI Studio with build_windows.py. No signature enforcement, activation service or lock prevents using modified LGPL libraries. BMK's MIT license permits application modifications and rebuilding.

## Other components

Installed distribution notices are in _internal/third_party_licenses, including Python, Pillow, NumPy, torch/torchvision, timm, ONNX Runtime, tokenizers, codecs and their bundled notices. inventory.json records the build environment's installed distributions; it is broader than the actual runtime file manifest.

NVIDIA CUDA 13.0 and cuDNN 9.24 runtime DLLs are included for this application's GPU features. Their EULAs are in licenses/ and at the official links below. These proprietary NVIDIA components are not covered by BMK's MIT license; their use and redistribution remain subject to NVIDIA's terms. They are not supplied as a standalone SDK or driver. CUPTI's companion Perfworks runtime is included as shipped with torch. No NVIDIA driver, compiler executable, private model weights or user files are bundled.

- CUDA 13.0 terms: https://docs.nvidia.com/cuda/archive/13.0.0/eula/index.html
- cuDNN terms: https://docs.nvidia.com/deeplearning/cudnn/backend/latest/reference/eula.html
- Qt LGPL obligations: https://www.qt.io/development/open-source-lgpl-obligations

Keep the notices, sources/access information and replacement instructions when redistributing this package. Model weights are downloaded separately and retain their model-card terms.

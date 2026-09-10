"""Bundle the inference runtime without its demonstration model weights."""
from PyInstaller.utils.hooks import collect_all
datas, binaries, hiddenimports = collect_all(
    "onnxruntime", exclude_datas=["**/*.onnx", "datasets/**"],
    filter_submodules=lambda name: not name.startswith("onnxruntime.datasets"))

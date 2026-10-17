"""Скачивает веса YOLOX (Apache-2.0) и делает вход динамическим, чтобы подавать портретные кадры.

  python tools/prepare_models.py            # models/yolox_s_dyn.onnx, models/yolox_tiny_dyn.onnx
"""
import sys
import urllib.request
from pathlib import Path

import onnx

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
URL = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/{}.onnx"


def main(names: list[str]) -> None:
    MODELS.mkdir(exist_ok=True)
    for name in names:
        src = MODELS / f"{name}.onnx"
        if not src.exists():
            print("скачиваю", name)
            urllib.request.urlretrieve(URL.format(name), src)
        m = onnx.load(str(src))
        d = m.graph.input[0].type.tensor_type.shape.dim
        d[2].dim_param, d[3].dim_param = "H", "W"
        m.graph.output[0].type.tensor_type.shape.dim[1].dim_param = "N"
        del m.graph.value_info[:]  # устаревшие подсказки о формах иначе дают предупреждения
        onnx.save(m, str(MODELS / f"{name}_dyn.onnx"))
        print("готово:", MODELS / f"{name}_dyn.onnx")


if __name__ == "__main__":
    main(sys.argv[1:] or ["yolox_s", "yolox_tiny"])

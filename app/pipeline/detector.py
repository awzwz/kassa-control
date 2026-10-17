"""Детектор людей и предметов: YOLOX (Apache-2.0) в ONNX Runtime.

Веса — официальные ONNX из релиза Megvii, вход сделан динамическим (tools/prepare_models.py),
поэтому портретный кадр 464×848 подаётся как 352×640 без обрезки. На CPU работает везде;
если в onnxruntime есть CUDA, используется видеокарта.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

COCO = ["person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
        "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
        "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
        "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
        "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
        "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
        "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard",
        "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
        "scissors", "teddy bear", "hair drier", "toothbrush"]
CLASS_ID = {name: i for i, name in enumerate(COCO)}

# Что нам вообще интересно в кассовой комнате. Остальные классы отбрасываем сразу.
KEEP = [CLASS_ID[c] for c in ("person", "backpack", "handbag", "suitcase", "bottle", "cup", "bowl", "chair",
                               "dining table", "tv", "laptop", "mouse", "keyboard", "cell phone", "book", "remote")]

MODELS_DIR = Path(os.environ.get("MODELS_DIR", Path(__file__).resolve().parents[2] / "models"))


@dataclass
class Detection:
    x1: float
    y1: float
    x2: float
    y2: float
    score: float
    cls: int

    @property
    def name(self) -> str:
        return COCO[self.cls]

    @property
    def box(self) -> tuple[float, float, float, float]:
        return self.x1, self.y1, self.x2, self.y2


class YOLOX:
    def __init__(self, name: str = "yolox_s_dyn", threads: int = 4) -> None:
        path = MODELS_DIR / f"{name}.onnx"
        if not path.exists():
            raise FileNotFoundError(f"нет весов {path}; запустите tools/prepare_models.py")
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        so.log_severity_level = 3  # глушим предупреждения о динамической форме выхода
        providers = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in ort.get_available_providers()]
        self.session = ort.InferenceSession(str(path), so, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.provider = self.session.get_providers()[0]
        self._grids: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}

    def _grid(self, h: int, w: int) -> tuple[np.ndarray, np.ndarray]:
        key = (h, w)
        if key not in self._grids:
            grids, strides = [], []
            for s in (8, 16, 32):
                hs, ws = h // s, w // s
                xv, yv = np.meshgrid(np.arange(ws), np.arange(hs))
                grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
                strides.append(np.full((hs * ws, 1), s))
            self._grids[key] = (np.concatenate(grids).astype(np.float32),
                                np.concatenate(strides).astype(np.float32))
        return self._grids[key]

    def __call__(self, img_bgr: np.ndarray, size: tuple[int, int] = (640, 352), conf: float = 0.25,
                 nms: float = 0.45, classes: list[int] | None = KEEP) -> list[Detection]:
        """size = (высота, ширина) входа, кратные 32. Координаты результата — в пикселях исходного кадра."""
        H, W = size
        h0, w0 = img_bgr.shape[:2]
        r = min(H / h0, W / w0)
        nh, nw = int(round(h0 * r)), int(round(w0 * r))
        canvas = np.full((H, W, 3), 114, np.uint8)
        canvas[:nh, :nw] = cv2.resize(img_bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
        x = canvas.transpose(2, 0, 1)[None].astype(np.float32)
        out = self.session.run(None, {self.input_name: x})[0][0]
        grid, stride = self._grid(H, W)
        xy = (out[:, :2] + grid) * stride
        wh = np.exp(out[:, 2:4]) * stride
        scores = out[:, 4:5] * out[:, 5:]
        cls = scores.argmax(1)
        sc = scores[np.arange(len(cls)), cls]
        keep = sc >= conf
        if classes is not None:
            keep &= np.isin(cls, classes)
        xy, wh, sc, cls = xy[keep], wh[keep], sc[keep], cls[keep]
        if not len(sc):
            return []
        boxes = np.concatenate([xy - wh / 2, xy + wh / 2], 1) / r
        boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, w0)
        boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, h0)
        result: list[Detection] = []
        for c in np.unique(cls):
            m = cls == c
            b, s = boxes[m], sc[m]
            xywh = np.concatenate([b[:, :2], b[:, 2:] - b[:, :2]], 1)
            idx = cv2.dnn.NMSBoxes(xywh.tolist(), s.tolist(), conf, nms)
            for i in np.array(idx).reshape(-1):
                result.append(Detection(*map(float, b[i]), float(s[i]), int(c)))
        result.sort(key=lambda d: -d.score)
        return result

from pathlib import Path
from threading import Lock

import cv2
import numpy as np


class TorchModel:
    """Local, trusted TorchScript weights. No network or random-weight fallback."""

    def __init__(self, path: Path, device: str) -> None:
        import torch

        self.torch = torch
        self.device = torch.device(device)
        self.lock = Lock()
        self.model = torch.jit.load(str(path), map_location=self.device).eval()

    def predict(self, bgr: np.ndarray, size: int, normalization: str) -> np.ndarray:
        rgb = cv2.cvtColor(cv2.resize(bgr, (size, size)), cv2.COLOR_BGR2RGB).astype(np.float32)
        if normalization == "facenet":
            rgb = (rgb - 127.5) / 128.0
        elif normalization == "imagenet":
            rgb = (rgb / 255.0 - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
        else:
            rgb = rgb / 255.0
        tensor = self.torch.from_numpy(np.ascontiguousarray(rgb.transpose(2, 0, 1))).unsqueeze(0).to(self.device)
        with self.lock, self.torch.inference_mode():
            result = self.model(tensor)
        if not isinstance(result, self.torch.Tensor) or result.ndim != 2 or result.shape[0] != 1:
            raise RuntimeError("Model contract requires a tensor shaped [1, N]")
        output = result.detach().float().cpu().numpy()[0]
        if not np.isfinite(output).all():
            raise RuntimeError("Model returned non-finite output")
        return output


def softmax(logits: np.ndarray, classes: int) -> np.ndarray:
    if logits.shape != (classes,):
        raise RuntimeError(f"Expected {classes} logits")
    values = np.exp(logits - logits.max())
    return values / values.sum()


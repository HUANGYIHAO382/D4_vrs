"""HSV 掩膜、形态学、轮廓检测与目标中心点。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np


@dataclass
class Detection:
    """单个轮廓检测结果（ROI 局部坐标）。"""

    cx: int
    cy: int
    x: int
    y: int
    w: int
    h: int
    area: float


@dataclass
class VisionConfig:
    lower_hsv: np.ndarray
    upper_hsv: np.ndarray
    min_area: float
    kernel_size: int
    dilate_iterations: int

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> "VisionConfig":
        return cls(
            lower_hsv=np.array(config["lower_hsv"], dtype=np.uint8),
            upper_hsv=np.array(config["upper_hsv"], dtype=np.uint8),
            min_area=float(config.get("min_area", 50)),
            kernel_size=int(config.get("kernel_size", 3)),
            dilate_iterations=int(config.get("dilate_iterations", 1)),
        )


class VisionPipeline:
    def __init__(self, vision_config: VisionConfig):
        self._cfg = vision_config

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "VisionPipeline":
        return cls(VisionConfig.from_dict(config))

    def build_mask(self, frame_bgr: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self._cfg.lower_hsv, self._cfg.upper_hsv)
        if self._cfg.dilate_iterations > 0:
            k = max(1, self._cfg.kernel_size)
            kernel = np.ones((k, k), np.uint8)
            mask = cv2.dilate(mask, kernel, iterations=self._cfg.dilate_iterations)
        return mask

    def find_detections(self, mask: np.ndarray) -> list[Detection]:
        contours = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = contours[-2]
        detections: list[Detection] = []
        for cnt in cnts:
            area = cv2.contourArea(cnt)
            if area < self._cfg.min_area:
                continue
            x, y, w, h = cv2.boundingRect(cnt)
            detections.append(
                Detection(
                    cx=x + w // 2,
                    cy=y + h // 2,
                    x=x,
                    y=y,
                    w=w,
                    h=h,
                    area=area,
                )
            )
        return detections

    def find_largest_target(self, mask: np.ndarray) -> Detection | None:
        detections = self.find_detections(mask)
        if not detections:
            return None
        return max(detections, key=lambda d: d.area)

    def process(self, frame_bgr: np.ndarray) -> tuple[np.ndarray, Detection | None]:
        mask = self.build_mask(frame_bgr)
        target = self.find_largest_target(mask)
        return mask, target


def draw_detection(frame: np.ndarray, det: Detection) -> None:
    x, y, w, h = det.x, det.y, det.w, det.h
    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
    cv2.circle(frame, (det.cx, det.cy), 5, (0, 0, 255), -1)

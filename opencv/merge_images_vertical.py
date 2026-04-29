import argparse
from pathlib import Path

import cv2
import numpy as np


def read_image(image_path: str) -> np.ndarray:
    data = np.fromfile(image_path, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"无法读取图片: {image_path}")
    return image


def write_image(image_path: str, image: np.ndarray) -> None:
    suffix = Path(image_path).suffix or ".jpg"
    success, encoded = cv2.imencode(suffix, image)
    if not success:
        raise ValueError(f"无法编码输出图片: {image_path}")
    encoded.tofile(image_path)


def resize_to_width(image: np.ndarray, target_width: int) -> np.ndarray:
    height, width = image.shape[:2]
    if width == target_width:
        return image
    target_height = int(round(height * target_width / width))
    return cv2.resize(image, (target_width, target_height), interpolation=cv2.INTER_AREA)


def merge_vertical(front_image: np.ndarray, back_image: np.ndarray, gap: int, background: int) -> np.ndarray:
    target_width = max(front_image.shape[1], back_image.shape[1])
    front = resize_to_width(front_image, target_width)
    back = resize_to_width(back_image, target_width)

    total_height = front.shape[0] + back.shape[0] + gap
    canvas = np.full((total_height, target_width, 3), background, dtype=np.uint8)
    canvas[: front.shape[0], : front.shape[1]] = front
    start_y = front.shape[0] + gap
    canvas[start_y : start_y + back.shape[0], : back.shape[1]] = back
    return canvas


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将两张图片按统一宽度上下拼接。")
    parser.add_argument("--front", required=True, help="上方图片路径")
    parser.add_argument("--back", required=True, help="下方图片路径")
    parser.add_argument("--output", required=True, help="输出图片路径")
    parser.add_argument("--gap", type=int, default=20, help="上下间距")
    parser.add_argument("--background", type=int, default=255, help="背景颜色，0-255")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    background = min(max(args.background, 0), 255)
    front_image = read_image(args.front)
    back_image = read_image(args.back)
    merged = merge_vertical(front_image, back_image, args.gap, background)
    write_image(args.output, merged)
    print(f"已生成文件: {args.output}")


if __name__ == "__main__":
    main()

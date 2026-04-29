import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


DEFAULT_WATERMARK = "本件仅用作软件著作权登记业务办理 其他用途无效"
DEFAULT_FONT = Path(__file__).with_name("NotoSansSC-VariableFont_wght.ttf")


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


def load_font(font_path: str | None, font_size: int) -> ImageFont.FreeTypeFont:
    candidates = []
    if font_path:
        candidates.append(Path(font_path))
    candidates.append(DEFAULT_FONT)

    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), font_size)
    raise FileNotFoundError("未找到可用中文字体，请通过 --font-path 指定字体文件。")


def fit_font_size(
    text: str,
    font_path: str | None,
    preferred_size: int,
    image_width: int,
    max_ratio: float = 0.2,
    min_size: int = 42,
) -> ImageFont.FreeTypeFont:
    font_size = max(preferred_size, min_size)
    while font_size >= min_size:
        font = load_font(font_path, font_size)
        bbox = font.getbbox(text)
        text_width = bbox[2] - bbox[0]
        if text_width <= image_width * max_ratio or font_size == min_size:
            return font
        font_size -= 2
    return load_font(font_path, min_size)


def add_tiled_watermark(
    image: np.ndarray,
    text: str,
    font_path: str | None,
    font_size: int,
    color: tuple[int, int, int],
    alpha: int,
    spacing_x: int,
    spacing_y: int,
    angle: float,
) -> np.ndarray:
    base = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).convert("RGBA")
    font = fit_font_size(text, font_path, font_size, base.width)

    bbox = font.getbbox(text)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    tile = Image.new("RGBA", (text_width + 20, text_height + 20), (255, 255, 255, 0))
    drawer = ImageDraw.Draw(tile)
    drawer.text((10, 10), text, font=font, fill=(*color, alpha))

    rotated_tile = tile.rotate(angle, expand=True)
    overlay = Image.new("RGBA", base.size, (255, 255, 255, 0))

    step_x = max(rotated_tile.width + spacing_x, 1)
    step_y = max(rotated_tile.height + spacing_y, 1)
    offset_x = 0
    offset_y = 0

    for row_index, y in enumerate(range(offset_y, overlay.height + rotated_tile.height, step_y)):
        row_shift = 0 if row_index % 2 == 0 else step_x // 2
        for x in range(offset_x - row_shift, overlay.width + rotated_tile.width, step_x):
            overlay.alpha_composite(rotated_tile, (x, y))

    merged = Image.alpha_composite(base, overlay).convert("RGB")
    return cv2.cvtColor(np.array(merged), cv2.COLOR_RGB2BGR)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="身份证正反面上下拼接并添加 45° 平铺文字水印。")
    parser.add_argument("--front", required=True, help="身份证正面图片路径")
    parser.add_argument("--back", required=True, help="身份证反面图片路径")
    parser.add_argument("--output", default="id_card_merged_watermarked.jpg", help="输出图片路径")
    parser.add_argument("--text", default=DEFAULT_WATERMARK, help="水印文字")
    parser.add_argument("--font-path", default=None, help="字体文件路径，未传时优先使用当前目录字体")
    parser.add_argument("--font-size", type=int, default=80, help="水印字体大小")
    parser.add_argument("--alpha", type=float, default=45, help="水印透明度百分比，范围 0-100")
    parser.add_argument("--spacing-x", type=int, default=-40, help="水印横向间距")
    parser.add_argument("--spacing-y", type=int, default=-20, help="水印纵向间距")
    parser.add_argument("--gap", type=int, default=20, help="正反面之间的垂直间距")
    parser.add_argument("--background", type=int, default=255, help="拼接背景颜色，0-255")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    alpha_percent = min(max(args.alpha, 0), 100)
    alpha = int(round(255 * alpha_percent / 100))
    background = min(max(args.background, 0), 255)

    front_image = read_image(args.front)
    back_image = read_image(args.back)
    merged_image = merge_vertical(front_image, back_image, gap=args.gap, background=background)
    watermarked_image = add_tiled_watermark(
        merged_image,
        text=args.text,
        font_path=args.font_path,
        font_size=args.font_size,
        color=(200, 30, 30),
        alpha=alpha,
        spacing_x=args.spacing_x,
        spacing_y=args.spacing_y,
        angle=45,
    )
    write_image(args.output, watermarked_image)
    print(f"已生成文件: {args.output}")


if __name__ == "__main__":
    main()

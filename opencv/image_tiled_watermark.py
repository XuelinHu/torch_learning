import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


DEFAULT_WATERMARK = "本件仅用于软件著作权登记办理 其他用途无效"
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
    max_ratio: float,
    min_size: int,
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
    min_font_size: int,
    width_ratio: float,
    color: tuple[int, int, int],
    alpha: int,
    stroke_color: tuple[int, int, int],
    stroke_alpha: int,
    stroke_width: int,
    spacing_x: int,
    spacing_y: int,
    angle: float,
) -> np.ndarray:
    base = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).convert("RGBA")
    font = fit_font_size(text, font_path, font_size, base.width, width_ratio, min_font_size)

    bbox = font.getbbox(text)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    padding = max(font.size // 3, 12)
    tile = Image.new("RGBA", (text_width + padding * 2, text_height + padding * 2), (255, 255, 255, 0))
    drawer = ImageDraw.Draw(tile)
    drawer.text(
        (padding, padding),
        text,
        font=font,
        fill=(*color, alpha),
        stroke_width=stroke_width,
        stroke_fill=(*stroke_color, stroke_alpha),
    )

    rotated_tile = tile.rotate(angle, expand=True)
    overlay = Image.new("RGBA", base.size, (255, 255, 255, 0))

    step_x = max(rotated_tile.width + spacing_x, 1)
    step_y = max(rotated_tile.height + spacing_y, 1)

    for row_index, y in enumerate(range(-rotated_tile.height // 2, overlay.height + rotated_tile.height, step_y)):
        row_shift = 0 if row_index % 2 == 0 else step_x // 2
        for x in range(-rotated_tile.width // 2 - row_shift, overlay.width + rotated_tile.width, step_x):
            overlay.alpha_composite(rotated_tile, (x, y))

    merged = Image.alpha_composite(base, overlay).convert("RGB")
    return cv2.cvtColor(np.array(merged), cv2.COLOR_RGB2BGR)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="为单张图片添加 45° 平铺斜向文字水印。")
    parser.add_argument("--input", required=True, help="输入图片路径")
    parser.add_argument("--output", required=True, help="输出图片路径")
    parser.add_argument("--text", default=DEFAULT_WATERMARK, help="水印文字")
    parser.add_argument("--font-path", default=None, help="字体文件路径，未传时优先使用当前目录字体")
    parser.add_argument("--font-size", type=int, default=88, help="水印字体大小")
    parser.add_argument("--min-font-size", type=int, default=44, help="最小水印字号")
    parser.add_argument("--width-ratio", type=float, default=0.28, help="单个水印相对图片宽度占比")
    parser.add_argument("--alpha", type=float, default=38, help="水印透明度百分比，范围 0-100")
    parser.add_argument("--spacing-x", type=int, default=40, help="水印横向间距")
    parser.add_argument("--spacing-y", type=int, default=28, help="水印纵向间距")
    parser.add_argument("--angle", type=float, default=45, help="水印旋转角度")
    parser.add_argument("--gray", type=int, default=120, help="水印灰度色值，0-255")
    parser.add_argument("--stroke-gray", type=int, default=100, help="水印描边灰度色值，0-255")
    parser.add_argument("--stroke-alpha", type=float, default=45, help="水印描边透明度百分比，范围 0-100")
    parser.add_argument("--stroke-width", type=int, default=1, help="水印描边宽度")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    alpha_percent = min(max(args.alpha, 0), 100)
    alpha = int(round(255 * alpha_percent / 100))
    gray = min(max(args.gray, 0), 255)
    stroke_alpha_percent = min(max(args.stroke_alpha, 0), 100)
    stroke_alpha = int(round(255 * stroke_alpha_percent / 100))
    stroke_gray = min(max(args.stroke_gray, 0), 255)

    image = read_image(args.input)
    watermarked = add_tiled_watermark(
        image=image,
        text=args.text,
        font_path=args.font_path,
        font_size=args.font_size,
        min_font_size=args.min_font_size,
        width_ratio=args.width_ratio,
        color=(gray, gray, gray),
        alpha=alpha,
        stroke_color=(stroke_gray, stroke_gray, stroke_gray),
        stroke_alpha=stroke_alpha,
        stroke_width=max(args.stroke_width, 0),
        spacing_x=args.spacing_x,
        spacing_y=args.spacing_y,
        angle=args.angle,
    )
    write_image(args.output, watermarked)
    print(f"已生成文件: {args.output}")


if __name__ == "__main__":
    main()

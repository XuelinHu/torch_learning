# -*- coding: utf-8 -*-
"""
dashcam_detect_cn_plate_auto_hf.py
- 通用目标检测（中文标签）
- 车牌检测并打码（自动下载 Hugging Face 权重）
- 正确处理 FP16（half）避免 dtype 冲突
"""

import os
import sys
import cv2
import time
import torch
import argparse
import numpy as np
from tqdm import tqdm
from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO

# -----------------------
# 车牌权重自动解析（方法 B）
# -----------------------
def resolve_weights(spec: str, filename: str = "best.pt") -> str:
    """
    如果 spec 是本地文件路径，直接返回。
    如果 spec 像 'user/repo'，自动从 Hugging Face 下载 filename（默认 best.pt）。
    """
    if os.path.exists(spec):
        return spec
    if "/" in spec and not spec.endswith(".pt"):
        try:
            from huggingface_hub import hf_hub_download
        except Exception as e:
            raise RuntimeError(
                "需要安装 huggingface_hub 才能从仓库自动下载权重：\n"
                "  python -m pip install -U huggingface_hub"
            ) from e
        print(f"[信息] 从 Hugging Face 下载权重：{spec}/{filename}")
        local_path = hf_hub_download(repo_id=spec, filename=filename)
        print(f"[信息] 权重下载到：{local_path}")
        return local_path
    raise FileNotFoundError(f"未找到模型：{spec}（既不是本地 .pt，也不是有效的 repo_id）")


# COCO 中文标签（按索引对应）
COCO80_ZH = [
    "行人","自行车","小汽车","摩托车","飞机","巴士","火车","卡车","船","红绿灯",
    "消防栓","停车标志","停车计时器","长椅","鸟","猫","狗","马","羊","牛",
    "大象","熊","斑马","长颈鹿","背包","雨伞","手提包","领带","行李箱","飞盘",
    "滑雪板","单板滑雪","运动球","风筝","棒球棒","棒球手套","滑板","冲浪板",
    "网球拍","瓶子","酒杯","杯子","叉子","刀","勺子","碗","香蕉","苹果",
    "三明治","橙子","西兰花","胡萝卜","热狗","披萨","甜甜圈","蛋糕","椅子","沙发",
    "盆栽","床","餐桌","马桶","电视","笔记本电脑","鼠标","遥控器","键盘","手机",
    "微波炉","烤箱","烤面包机","水槽","冰箱","书","钟表","花瓶","剪刀","泰迪熊",
    "吹风机","牙刷"
]
AUTO_CLASSES = {"行人","小汽车","巴士","卡车","摩托车","自行车"}


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="输入视频路径")
    ap.add_argument("--output", required=True, help="输出视频路径（.mp4）")
    ap.add_argument("--model", default="yolov8s.pt", help="目标检测模型（COCO，支持本地 .pt）")
    ap.add_argument("--conf", type=float, default=0.25, help="目标检测置信度")
    ap.add_argument("--imgsz", type=int, default=960, help="目标检测输入尺寸")
    ap.add_argument("--classes", type=str, default="all", help='筛选类别："all" | "auto" | "行人,小汽车,..."')
    ap.add_argument("--show", action="store_true", help="边推理边显示窗口")
    ap.add_argument("--half", action="store_true", help="FP16 半精度（CUDA）")
    ap.add_argument("--max_frames", type=int, default=-1, help="仅处理前 N 帧")
    ap.add_argument("--font", type=str, default="", help="中文字体（如 NotoSansSC-Regular.otf）")
    ap.add_argument("--fontsize", type=int, default=32, help="中文标签字号")
    ap.add_argument("--box_thick", type=int, default=3, help="目标框线宽")

    # 车牌相关（自动下载）
    ap.add_argument("--plate_model", type=str,
                    default="yasirfaizahmed/license-plate-object-detection",
                    help="车牌模型（本地 .pt 或 HF 仓库 user/repo）")
    ap.add_argument("--plate_filename", type=str, default="best.pt",
                    help="HF 仓库中的权重文件名（默认 best.pt）")
    ap.add_argument("--plate_conf", type=float, default=0.35, help="车牌检测置信度")
    ap.add_argument("--plate_imgsz", type=int, default=960, help="车牌检测输入尺寸")
    ap.add_argument("--blur", type=str, default="mosaic", choices=["mosaic","gauss"], help="打码方式")
    ap.add_argument("--blur_strength", type=int, default=25, help="打码强度（mosaic=块大小，gauss=核尺寸，需奇数）")
    ap.add_argument("--draw_obj_boxes", action="store_true", help="是否绘制所有目标框（默认不画只打码车牌）")
    return ap.parse_args()


def build_class_filter(spec: str):
    if spec.lower() == "all":
        return None
    keep = AUTO_CLASSES if spec.lower() == "auto" else set([s.strip() for s in spec.split(",") if s.strip()])
    idx = [i for i, name in enumerate(COCO80_ZH) if name in keep]
    return idx if idx else None


def pick_fourcc():
    for cc in ["mp4v", "avc1", "H264", "XVID"]:
        yield cc, cv2.VideoWriter_fourcc(*cc)


def ensure_font(path: str, size: int):
    try:
        if path and os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    except Exception:
        pass
    for candidate in ["NotoSansSC-Regular.otf", "NotoSansSC-VariableFont_wght.ttf",
                      "SimHei.ttf", "Microsoft YaHei.ttf", "PingFang.ttc"]:
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def blur_region(img, x1, y1, x2, y2, method="mosaic", strength=25):
    h, w = img.shape[:2]
    x1, y1, x2, y2 = map(int, [clamp(x1, 0, w - 1), clamp(y1, 0, h - 1),
                               clamp(x2, 0, w - 1), clamp(y2, 0, h - 1)])
    if x2 <= x1 or y2 <= y1:
        return img
    roi = img[y1:y2, x1:x2]
    if method == "mosaic":
        s = max(5, int(strength))
        small = cv2.resize(roi, (max(1, (x2 - x1) // s), max(1, (y2 - y1) // s)), interpolation=cv2.INTER_LINEAR)
        roi_blur = cv2.resize(small, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST)
    else:
        k = strength if strength % 2 == 1 else strength + 1
        k = max(5, k)
        roi_blur = cv2.GaussianBlur(roi, (k, k), 0)
    img[y1:y2, x1:x2] = roi_blur
    return img


def main():
    args = parse_args()

    if not os.path.exists(args.input):
        print(f"[错误] 找不到输入视频：{args.input}")
        sys.exit(1)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    safe_half = bool(args.half and device == "cuda")

    # 目标检测模型（人/车等）
    det_model = YOLO(args.model).to(device)

    # 车牌检测模型（本地或自动下载）
    plate_w = resolve_weights(args.plate_model, filename=args.plate_filename)
    plate_model = YOLO(plate_w).to(device)

    class_filter = build_class_filter(args.classes)

    cap = cv2.VideoCapture(args.input)
    if not cap.isOpened():
        print(f("[错误] 无法打开视频：{args.input}"))
        sys.exit(1)

    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps    = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or None

    out, chosen = None, None
    for name, fourcc in pick_fourcc():
        out = cv2.VideoWriter(args.output, fourcc, fps, (width, height))
        if out.isOpened():
            chosen = name
            break
    if out is None or not out.isOpened():
        print("[错误] 无法创建输出视频。尝试 .avi 或安装 H.264 编码器。")
        sys.exit(1)
    print(f"[信息] 编码器：{chosen}, 分辨率 {width}x{height} @ {fps:.2f} FPS")

    font = ensure_font(args.font, args.fontsize)

    pbar = tqdm(total=total, desc="Processing", unit="f")
    frame_id, t0 = 0, time.time()

    try:
        while True:
            ret, frame_bgr = cap.read()
            if not ret:
                break
            frame_id += 1
            if args.max_frames > 0 and frame_id > args.max_frames:
                break

            # 1) 车牌检测并打码（优先保护隐私）
            plate_res = plate_model.predict(
                source=frame_bgr,
                imgsz=args.plate_imgsz,
                conf=args.plate_conf,
                device=0 if device == "cuda" else "cpu",
                half=safe_half,
                verbose=False
            )[0]
            if plate_res.boxes is not None and len(plate_res.boxes) > 0:
                p_boxes = plate_res.boxes.xyxy.cpu().numpy()
                for (px1, py1, px2, py2) in p_boxes:
                    frame_bgr = blur_region(
                        frame_bgr, int(px1), int(py1), int(px2), int(py2),
                        method=args.blur, strength=args.blur_strength
                    )

            # 2) 通用目标检测（可选画框+中文标签）
            det_res = det_model.predict(
                source=frame_bgr,          # 对打码后的图再检测无妨
                imgsz=args.imgsz,
                conf=args.conf,
                device=0 if device == "cuda" else "cpu",
                half=safe_half,
                verbose=False
            )[0]

            if args.draw_obj_boxes and det_res.boxes is not None and len(det_res.boxes) > 0:
                boxes = det_res.boxes.xyxy.cpu().numpy()
                confs = det_res.boxes.conf.cpu().numpy()
                clses = det_res.boxes.cls.cpu().numpy().astype(int)

                # PIL 画中文标签（OpenCV putText 不支持中文）
                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(frame_rgb)
                draw = ImageDraw.Draw(pil_img)

                for (x1, y1, x2, y2), c, cls in zip(boxes, confs, clses):
                    if not (0 <= cls < len(COCO80_ZH)):
                        continue
                    if class_filter is not None and cls not in class_filter:
                        continue

                    label_zh = COCO80_ZH[cls]
                    text = f"{label_zh} {c:.2f}"
                    x1, y1, x2, y2 = map(int, [x1, y1, x2, y2])

                    # 画框（OpenCV 更快）
                    cv2.rectangle(frame_bgr, (x1, y1), (x2, y2), (0, 255, 0), args.box_thick)

                    # 文本背景+文字（PIL）
                    tw, th = draw.textbbox((0, 0), text, font=font)[2:]
                    pad = 4
                    tx1, ty1 = x1, max(0, y1 - th - 10)
                    tx2, ty2 = x1 + tw + pad * 2, ty1 + th + pad * 2
                    draw.rectangle([tx1, ty1, tx2, ty2], fill=(0, 255, 0))
                    draw.text((tx1 + pad, ty1 + pad), text, font=font, fill=(0, 0, 0))

                frame_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

            out.write(frame_bgr)

            if args.show:
                cv2.imshow("Detections (ZH + Plates Blur)", frame_bgr)
                if cv2.waitKey(1) & 0xFF == 27:
                    break

            pbar.update(1)

    finally:
        cap.release()
        out.release()
        if args.show:
            cv2.destroyAllWindows()
        pbar.close()
        dt = time.time() - t0
        print(f"[完成] {frame_id} 帧，用时 {dt:.1f}s，平均 {frame_id/max(dt,1e-6):.1f} FPS")
        print(f"[输出] {os.path.abspath(args.output)}")


if __name__ == "__main__":
    main()
"""

python dashcam_detect_cn.py \
  --input  /home/deipss/Videos/drivers/city_to_school.MP4 \
  --output /home/deipss/Videos/drivers/city_to_school_P.MP4 \
  --model yolov8s.pt \
  --fontsize 34 --box_thick 4 \
  --font NotoSansSC-VariableFont_wght.ttf \
  --plate_model yasirfaizahmed/license-plate-object-detection \
  --plate_filename best.pt \
  --plate_conf 0.35 \
  --blur mosaic --blur_strength 20 \
  --draw_obj_boxes

"""
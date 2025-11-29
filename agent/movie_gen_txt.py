from moviepy import *
import os
import numpy as np

from PIL import Image, ImageDraw
import datetime

import textwrap

def gen_txt():
    fps = 60

    # 设置资源路径
    audio_paths = ["audios/vallex_generation.wav", "audios/vallex_generation2.wav"]  # 替换为你的音频文件路径
    image_paths = ["images/quantum.png", "images/environment.png"]  # 确保所有图片文件存在
    txts = [
        '用户可能是学生、开发者或者对硬件性能感兴趣的人。如果是学生或刚入行的开发者，他们可能需要了解TFLOPS在评估GPU性能时的作用，以便在购买或使用GPU时做出明智的选择。',
        '我需要考虑用户可能存在的深层需求。他们可能不仅仅想知道TFLOPS的定义，还想了解如何将其应用到实际场景中,以便在购买或使用GPU时做出明智的选择。']
    background_image_path = "images/white_background_with_orange_border.png"  # 背景图片路径
    output_path = "vedios/final_video4.mp4"  # 最终视频输出路径
    # 加载背景图片并获取其尺寸
    bg_image_clip = ImageClip(background_image_path).with_fps(fps)
    bg_width, bg_height = bg_image_clip.size  # 获取背景图片的宽高
    bg_width -= 25
    bg_height -= 25
    # 计算总时长（所有音频的总时长）
    total_duration = sum(AudioFileClip(audio).duration for audio in audio_paths)
    # 创建背景视频剪辑，持续时间为所有音频总时长
    background_clip = bg_image_clip.with_duration(total_duration)
    video_clips = []
    # 遍历音频和对应图片，生成视频片段
    current_time = 0  # 当前累计时间
    # ... existing code ...
    for audio_file, image_file, txt in zip(audio_paths, image_paths, txts):


        # 加载音频
        audio_clip = AudioFileClip(audio_file)
        duration = audio_clip.duration


        # 加载图像并检查尺寸
        img = Image.open(image_file)
        img_width, img_height = img.size

        # 计算最大允许尺寸(背景尺寸的40%)
        max_width = bg_width * 0.7
        max_height = bg_height * 0.7

        # 如果需要缩放
        if img_width > max_width or img_height > max_height:
            # 计算缩放比例
            width_ratio = max_width / img_width
            height_ratio = max_height / img_height
            scale = min(width_ratio, height_ratio)

            # 应用缩放
            new_width = int(img_width * scale)
            new_height = int(img_height * scale)
            img = img.resize((new_width, new_height), Image.LANCZOS)
            img.save(image_file)  # 覆盖原文件或保存到临时文件
            img_width, img_height = new_width, new_height  # Update dimensions after resize

            # 加载图像作为前景
        image_clip = (ImageClip(image_file)
                      .with_duration(duration)
                      .with_audio(audio_clip)
                      .with_position(("center", "center"))
                      .with_fps(fps))
        print(txt)
        wrapped_text = textwrap.fill(txt, width=30)

        txt_clip = (TextClip(font='./font/simhei.ttf', text=wrapped_text, font_size=50, color='#000000',bg_color='#FFCC99',
                             size=(bg_width-200, 200), method='caption')
                    .with_duration(duration)
                    .with_position(("center","bottom")))
        video = CompositeVideoClip([image_clip,txt_clip], size=(bg_width, bg_height))
        video_clips.append(video)
        current_time += duration  # 更新当前累计时间
    # 合并所有片段
    foreground_videos = concatenate_videoclips(video_clips, method="compose")

    # 将前景视频和字幕合并到背景上
    final_video = CompositeVideoClip(size=(1920, 1080), clips=[background_clip, foreground_videos])
    # 导出最终视频
    final_video.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=24)


if __name__ == '__main__':
    gen_txt()

from PIL import Image
import os


def adjust_image(filepath, target_dir):
    """
    调整图片大小和质量以满足指定条件，并保存到目标目录。

    :param filepath: 原始图片路径
    :param target_dir: 目标保存目录
    """
    try:
        with Image.open(filepath) as img:
            # 调整尺寸
            file_size_kb = os.path.getsize(filepath) / 1024
            if img.size == (240, 320) and 15 <= file_size_kb <= 20:
                print(f'OK :{filepath} ')
                return
            img = img.resize((240, 320), Image.LANCZOS)

            # 确定保存路径
            filename = os.path.basename(filepath)

            save_path = os.path.join(target_dir, filename)

            # 尝试通过改变JPEG质量设置来调整文件大小
            for quality in range(100, 60, 1):  # 从高质量到低质量尝试
                img.save(save_path, "JPEG", quality=quality)
                file_size_kb = os.path.getsize(save_path) / 1024

                if 15 <= file_size_kb <= 20:
                    print(f"成功调整: {filename} 至 {file_size_kb:.2f} KB")
                    return
            else:
                print(f"无法将 {filename} 调整至所需大小范围.")

    except Exception as e:
        print(f"处理图片 {filepath} 时出错: {e}")


def process_images(directory):
    """
    遍历目录下的所有图片，检查并调整它们。

    :param directory: 包含图片的目录路径
    """
    target_directory = os.path.join(directory, "adjusted_images")
    if not os.path.exists(target_directory):
        os.makedirs(target_directory)

    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(".jpg"):
                filepath = os.path.join(root, file)
                adjust_image(filepath, target_directory)


if __name__ == '__main__':

    # 使用时请将这里的路径替换为你想要处理的文件夹路径
    directory_to_process ='/Users/deipss/Desktop/LZTD/a宁局:沿海2025届2+1/学生资格证/图片'
    process_images(directory_to_process)
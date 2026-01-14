import os
import sys
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd


# =========================
# 可配置参数（按需修改）
# =========================
DEFAULT_INPUT_DIR = "D:\\edu_lt\\教案\\信息技术2-胡学林\\超星作业"          # 默认处理当前目录
DEFAULT_OUTPUT_DIR = None        # 默认输出到 input_dir（为 None 时）
START_ROW = 2                    # 学生数据从第3行开始（0-based 索引：2）
COL_STUDENT_ID = 0               # 学号列索引
COL_NAME = 1                     # 姓名列索引
COL_CLASS = 5                    # 班级列索引
COL_SCORE = 8                    # 分数列索引（第9列）
SKIP_KEYWORD = "汇总"            # 文件名包含该关键词则跳过


def setup_logger(log_dir: Path) -> str:
    """配置日志系统，返回日志文件名"""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_filename = log_dir / f'成绩整理日志_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            logging.StreamHandler(sys.stdout),
        ]
    )

    # Windows 控制台编码兼容
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    logging.info("程序启动")
    logging.info(f"当前工作目录: {os.getcwd()}")
    logging.info(f"日志文件: {log_filename}")
    return str(log_filename)


def should_skip_file(filename: str) -> bool:
    """判断是否应该跳过该文件（临时文件、缓存文件、汇总文件等）"""
    if SKIP_KEYWORD in filename:
        return True

    # Windows 临时文件
    if filename.startswith('~$'):
        return True

    # macOS 系统文件
    if filename.startswith('.DS_Store') or filename.startswith('._'):
        return True

    # Linux/Unix 临时文件
    if filename.startswith('.~') or filename.startswith('~'):
        return True
    if filename.startswith('#') and filename.endswith('#'):
        return True

    # 临时文件扩展名
    temp_extensions = ['.tmp', '.temp', '.bak', '.swp', '.cache']
    if any(filename.lower().endswith(ext) for ext in temp_extensions):
        return True

    return False


def list_excel_files(input_dir: Path) -> list[Path]:
    files = sorted([
        p for p in input_dir.iterdir()
        if p.is_file()
        and p.suffix.lower() == ".xlsx"
        and not should_skip_file(p.name)
    ])
    return files


def process_one_file(xlsx_path: Path) -> tuple[str | None, pd.DataFrame | None]:
    """
    处理单个Excel，返回 (班级名, 学生子表)
    班级名取第一个学生的班级；如果没有有效学生数据，返回 (None, None)
    """
    hw_name = xlsx_path.stem
    logging.info(f"\n处理文件: {xlsx_path.name}")

    df = pd.read_excel(xlsx_path)
    logging.info(f"  文件读取成功，共 {len(df)} 行")

    student_data = df.iloc[START_ROW:].copy()
    if student_data.empty:
        logging.warning("  文件中无学生数据（空表）")
        return None, None

    # 重命名列为 0..n-1，便于按索引取列
    student_data.columns = range(len(student_data.columns))

    # 基础字段
    student_data['学号'] = student_data[COL_STUDENT_ID]
    student_data['姓名'] = student_data[COL_NAME]
    student_data['班级'] = student_data[COL_CLASS]
    student_data[hw_name] = student_data[COL_SCORE]

    # 只保留需要的列，并剔除学号为空的行
    student_data = student_data[['学号', '姓名', '班级', hw_name]].dropna(subset=['学号'])

    if student_data.empty:
        logging.warning("  未找到有效学生记录（学号为空/被过滤）")
        return None, None

    class_name = str(student_data.iloc[0]['班级'])
    logging.info(f"  检测到班级: {class_name}，学生数: {len(student_data)}")
    return class_name, student_data


def merge_class_data(class_data: dict[str, pd.DataFrame], class_name: str, student_subset: pd.DataFrame) -> None:
    """把一个文件的学生成绩合并进班级汇总表"""
    if class_name not in class_data or class_data[class_name].empty:
        class_data[class_name] = student_subset.copy()
        logging.info(f"  创建/初始化班级汇总: {class_name}")
        return

    class_data[class_name] = class_data[class_name].merge(
        student_subset,
        on=['学号', '姓名', '班级'],
        how='outer'
    )


def save_results(class_data: dict[str, pd.DataFrame], output_dir: Path) -> None:
    logging.info("\n开始保存汇总结果")
    output_dir.mkdir(parents=True, exist_ok=True)

    for class_name, df in class_data.items():
        class_name_clean = str(class_name).replace('/', '-').replace('\\', '-')
        df = df.sort_values('学号').reset_index(drop=True)

        output_file = output_dir / f'{class_name_clean}成绩汇总表.xlsx'
        try:
            df.to_excel(output_file, index=False)
            logging.info(f"{class_name}: {len(df)}人, 保存到 {output_file}")
            logging.info(f"  成绩列数: {len(df.columns) - 3} (学号、姓名、班级除外)")
        except Exception as e:
            logging.error(f"保存 {output_file} 时出错: {e}")


def main(input_dir: str = DEFAULT_INPUT_DIR, output_dir: str | None = DEFAULT_OUTPUT_DIR) -> None:
    input_path = Path(input_dir).resolve()
    if not input_path.exists() or not input_path.is_dir():
        raise NotADirectoryError(f"输入目录不存在或不是文件夹: {input_path}")

    out_path = Path(output_dir).resolve() if output_dir else input_path

    # 日志写到输出目录（更方便找）
    setup_logger(out_path)

    files = list_excel_files(input_path)
    logging.info(f"找到 {len(files)} 个有效 Excel 文件")
    for p in files:
        logging.info(f"  - {p.name}")

    class_data: dict[str, pd.DataFrame] = {}

    for xlsx in files:
        try:
            class_name, student_subset = process_one_file(xlsx)
            if class_name and student_subset is not None:
                merge_class_data(class_data, class_name, student_subset)
        except Exception as e:
            logging.error(f"  处理文件 {xlsx.name} 时出错: {e}")
            continue

    save_results(class_data, out_path)
    logging.info("\n程序执行完成")


if __name__ == "__main__":
    # 这里改路径即可：
    # main(input_dir=r"D:\你的成绩文件夹", output_dir=r"D:\输出文件夹")
    main()

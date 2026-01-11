import pandas as pd
import os
import sys
import logging
from datetime import datetime

# 配置日志系统
log_filename = f'成绩整理日志_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

sys.stdout.reconfigure(encoding='utf-8')
logging.info("程序启动")
logging.info(f"工作目录: {os.getcwd()}")

def should_skip_file(filename):
    """判断是否应该跳过该文件（临时文件、缓存文件等）"""
    # 排除汇总文件
    if '汇总' in filename:
        return True

    # Windows 临时文件
    if filename.startswith('~$'):
        return True

    # macOS 系统文件
    if filename.startswith('.DS_Store') or filename.startswith('._'):
        return True

    # Linux/Unix 临时文件
    if filename.startswith('.~') or filename.startswith('~') or filename.startswith('#') and filename.endswith('#'):
        return True

    # 临时文件扩展名
    temp_extensions = ['.tmp', '.temp', '.bak', '.swp', '.cache']
    if any(filename.lower().endswith(ext) for ext in temp_extensions):
        return True

    return False

# 获取所有文件（排除临时文件、缓存文件和汇总文件）
all_files = sorted([
    f for f in os.listdir('.')
    if f.endswith('.xlsx') and not should_skip_file(f)
])

logging.info(f"找到{len(all_files)}个有效文件")
for f in all_files:
    logging.info(f"  - {f}")

# 用字典存储每个班级的成绩数据
class_data = {}  # 格式: {班级名: DataFrame}

# 遍历每个文件
for hw_file in all_files:
    # 生成作业/实验名称（去掉.xlsx后缀）
    hw_name = hw_file.replace('.xlsx', '')
    logging.info(f"\n处理文件: {hw_file}")

    try:
        # 读取Excel文件
        df = pd.read_excel(hw_file)
        logging.info(f"  文件读取成功，共{len(df)}行数据")

        # 提取学生数据（从第3行开始，索引为2）
        student_data = df.iloc[2:].copy()

        # 重命名列以便访问
        student_data.columns = range(len(student_data.columns))

        # 提取学号、姓名、班级、分数
        student_data['学号'] = student_data[0]
        student_data['姓名'] = student_data[1]
        student_data['班级'] = student_data[5]
        student_data[hw_name] = student_data[8]  # 分数在第9列（索引8）

        # 选择需要的列
        student_data = student_data[['学号', '姓名', '班级', hw_name]].dropna(subset=['学号'])

        # 判断该文件属于哪个班级（从第一个学生数据中获取班级）
        if len(student_data) > 0:
            first_student_class = student_data.iloc[0]['班级']
            logging.info(f"  检测到班级: {first_student_class}, 学生数: {len(student_data)}")

            # 如果该班级还没有DataFrame，创建一个
            if first_student_class not in class_data:
                class_data[first_student_class] = pd.DataFrame(columns=['学号', '姓名', '班级'])
                logging.info(f"  创建新班级: {first_student_class}")

            # 合并到对应班级的DataFrame
            class_df = class_data[first_student_class]
            student_subset = student_data[['学号', '姓名', '班级', hw_name]]

            if len(class_df) == 0:
                class_data[first_student_class] = student_subset.copy()
            else:
                class_data[first_student_class] = class_df.merge(
                    student_subset,
                    on=['学号', '姓名', '班级'],
                    how='outer'
                )
        else:
            logging.warning(f"  文件中未找到有效学生数据")

    except Exception as e:
        logging.error(f"  处理文件 {hw_file} 时出错: {str(e)}")
        continue

# 保存结果
logging.info("\n开始保存汇总结果")
for class_name, df in class_data.items():
    # 清理班级名称（用于文件名）
    class_name_clean = class_name.replace('/', '-').replace('\\', '-')

    # 按学号排序
    df = df.sort_values('学号').reset_index(drop=True)

    # 保存文件
    output_file = f'{class_name_clean}成绩汇总表.xlsx'
    try:
        df.to_excel(output_file, index=False)
        logging.info(f"{class_name}: {len(df)}人, 保存到 {output_file}")
        logging.info(f"  成绩列数: {len(df.columns)-3} (学号、姓名、班级除外)")
    except Exception as e:
        logging.error(f"保存 {output_file} 时出错: {str(e)}")

logging.info("\n程序执行完成")
logging.info(f"日志已保存到: {log_filename}")

import cdsapi
import os
from time import sleep
if __name__ == '__main__':

        # 创建输出目录（如果不存在）
    output_dir = "./"

    # 数据集配置
    dataset = "derived-era5-single-levels-daily-statistics"

    # 定义要下载的年份
    years = ['2012', '2013', '2014', '2015', '2016', '2017', '2018', '2019', '2020', '2021']  # 可以扩展为 ['2012', '2013', ...]
    months = ["01", "02", "03", "04", "05", "06",
              "07", "08", "09", "10", "11", "12"]

    # 变量列表保持不变
    variables = [
        "surface_net_solar_radiation",
        "surface_net_solar_radiation_clear_sky",
        "surface_solar_radiation_downward_clear_sky",
        "surface_solar_radiation_downwards",
        "toa_incident_solar_radiation",
        "top_net_solar_radiation",
        "top_net_solar_radiation_clear_sky",
        "total_cloud_cover",
        "total_column_water_vapour"
    ]

    # 创建CDS客户端
    client = cdsapi.Client()

    for year in years:
        for month in months:
            # 构造请求参数
            request = {
                "product_type": "reanalysis",
                "variable": variables,  # 使用完整的变量列表
                "year": [year],
                "month": [month],
                "day": [f"{day:02d}" for day in range(1, 32)],  # 所有日期
                "daily_statistic": "daily_mean",
                "time_zone": "utc+00:00",
                "frequency": "1_hourly",
                "area": [36.623, -116.019, 36.623, -116.019]
            }

            # 构造输出文件名
            filename = f"ERA5_{year}_{month}.nc"
            output_path = os.path.join(output_dir, filename)

            try:
                print(f"正在下载 {year}年{month}月数据...")

                # 执行下载
                client.retrieve(dataset, request).download(output_path)

                print(f"成功下载: {filename}")
                sleep(60)  # 每次下载后暂停60秒，避免请求过于频繁

            except Exception as e:
                print(f"下载失败: {str(e)}")
                if "cost limits exceeded" in str(e):
                    print("检测到请求量过大，将尝试减少请求天数...")
                    # 尝试只下载前15天
                    request["day"] = [f"{day:02d}" for day in range(1, 16)]
                    try:
                        client.retrieve(dataset, request).download(output_path)
                        print(f"成功下载前半月的{filename}")
                    except Exception as e2:
                        print(f"仍然失败: {str(e2)}")
                        print("请稍后再试或进一步减少请求量")
                continue

    print("所有数据下载完成！")
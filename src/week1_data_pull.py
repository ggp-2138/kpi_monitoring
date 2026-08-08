import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

#prometheus服务运行的ip和端口(docker-compose文件配置了宿主机和容器端口映射)
PROMETHEUS_URL = "http://xxx:9090"

# 使用PromQL语言查询过去1小时的 api_latency_seconds 指标（histogram 取 sum/count 算均值）
# api_latency_seconds: Histogram 直方图类型指标
# _sum: 区间内所有请求延迟总和
# _count: 区间内总请求次数
# [1m]: 时间窗口 1 分钟,代表取最近 1 分钟的采样点计算速率
query = 'rate(api_latency_seconds_sum[1m]) / rate(api_latency_seconds_count[1m])'

#获取当前本地系统时间
end = datetime.now()

# timedelta(hours=1): 生成 1 小时的时间差对象
start = end - timedelta(hours=1)

# API 请求参数字典
# timestamp(): 把时间转为Unix 秒级时间戳(Prometheus API 只识别时间戳)
params = {
    'query': query,
    'start': start.timestamp(),
    'end': end.timestamp(),
    'step': '15s'   # 匹配数据点抓取间隔
}

#发送 GET 请求
resp = requests.get(f"{PROMETHEUS_URL}/api/v1/query_range", params=params)

#转为 Python 字典/列表，存入data
data = resp.json()
# print("data",data)
# 解析结果
results = data['data']['result']
if results:
    values = results[0]['values']       # 列表中每个元素 [[timestamp_1, value_1],[timestamp_2, value_2]...]
    df = pd.DataFrame(values, columns=['timestamp', 'latency'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')     #转换时间戳(秒级)列为可读日期时间
    df['latency'] = df['latency'].astype(float)     #转成浮点小数
    print(df.head())
else:
    print("No data returned")

# MAD (threshold值越大检测越严格,阈值取2σ,对应threshold=2)
# MAD算法相较于 3-sigma算法 不受极端大延迟干扰
#公式
# σ≈1.4826*MAD
# 0.6745*(x−med)     x-med
# ————————————— =  —————————
#     MAD          1.4826*MAD
def mad_detect(series, threshold=2):
    #计算序列中位数
    median = series.median()

    #计算MAD: 绝对偏差的中位数
    mad = np.median(np.abs(series - median))

    # 避免 mad 为 0 时除以 0
    if mad == 0:
        mad = 1e-6

    #修正 Z 分数绝对值越大，代表当前点偏离中位数越远
    # |modified_z_scores| >threshold 判定为异常
    # 0.6745 是一个缩放因子，让 MAD 和标准差在正态分布下具有可比性（即 MAD ≈ 0.6745 * σ）
    modified_z_scores = 0.6745 * (series - median) / mad

    # return np.abs(modified_z_scores) > threshold
    #去掉 abs 过滤延迟低的异常值,只检测延迟高的
    return modified_z_scores > threshold            #检测到异常值则返回True

df['is_anomaly'] = mad_detect(df['latency'])
print(df[df['is_anomaly']])  # 打印异常点

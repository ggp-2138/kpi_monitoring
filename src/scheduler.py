import requests
import json
import hmac
import hashlib
import base64
import urllib.parse
import time
import sys
from datetime import datetime, timedelta

# ========== 配置区 ==========
PROMETHEUS_URL = "http://xxx:9090"  # 虚拟机 Prometheus 地址
DETECT_API_URL = "http://xxx:8000/detect"  # Windows FastAPI 服务地址（注意这里要填你 Windows 的 IP）
WEBHOOK_URL = "xxx"  # 替换为你的钉钉机器人 Webhook
SECRET = "xxx"  # 钉钉生成的 SEC
QUERY = 'rate(api_latency_seconds_sum[1m]) / rate(api_latency_seconds_count[1m])'
MAD_THRESHOLD = 3  # 异常检测阈值，可根据实际情况在 /detect 接口调整

# ========== 1. 从 Prometheus 拉取数据 ==========
# 调用 Prometheus API 接口，拉取指定时间窗口的延迟数据，返回数值列表和对应时间戳列表
def fetch_from_prometheus(minutes):
    end = datetime.now()
    start = end - timedelta(minutes=minutes)
    params = {
        'query': QUERY,
        'start': start.timestamp(),
        'end': end.timestamp(),
        'step': '15s'
    }
    # /query_range: Prometheus 范围查询接口
    # params=params: URL查询参数
    resp = requests.get(f"{PROMETHEUS_URL}/api/v1/query_range", params=params, timeout=10)
    data = resp.json()  # 将 json 字符串解析为 Python 字典(自动处理编码)
    print(data)
    results = data['data']['result']
    if not results:
        print("[INFO] 没有查询到数据")
        return None, None
    values = [float(v[1]) for v in results[0]['values']]  # 时间序列延迟部分
    timestamps = [v[0] for v in results[0]['values']]  # 时间戳
    print(f"[INFO] 拉取到 {len(values)} 个数据点")
    return values, timestamps


# ========== 2. 调用 /detect 接口 ==========
# 调用远端 /detect 异常检测接口，传入延迟数据，返回异常点列表
def detect_anomalies(values):
    #请求头
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer my-secret-token"
    }
    # json={}: 请求体参数
    resp = requests.post(DETECT_API_URL, json={"values": values},headers=headers,timeout=10)
    result = resp.json()
    anomalies = result.get("anomalies", [])  # 获取异常点列表,为空则返回[]
    # result 格式示例: {"anomalies": [{"index": 3,"value": 0.8},{"index": 5,"value": 0.9}]}
    print(f"[INFO] 检测到 {len(anomalies)} 个异常点")
    return anomalies


# ========== 3. 发送钉钉告警 ==========
# 把异常信息整理为钉钉 Markdown 格式，调用机器人接口发送告警
def send_dingtalk_alert(anomalies, timestamps):
    if not anomalies:
        print("[INFO] 无异常，跳过告警")
        return

    # 加签计算
    #生成毫秒时间戳
    #签名和时间戳绑定，过期的签名会失效，避免被截获后重复利用
    timestamp = str(round(time.time() * 1000))

    #构造待签名字符串(按照钉钉官方规范)
    sign_str = f"{timestamp}\n{SECRET}"

    #HMAC-SHA256 签名计算
    #以 SECRET 为密钥，对 sign_str 做 HMAC-SHA256 哈希运算
    #对哈希后的二进制结果做 Base64 编码
    sign = base64.b64encode(hmac.new(
        SECRET.encode(), sign_str.encode(), hashlib.sha256
    ).digest())

    #对签名结果做 URL 编码
    sign_encoded = urllib.parse.quote_plus(sign)
    url = f"{WEBHOOK_URL}&timestamp={timestamp}&sign={sign_encoded}"

    # 构造异常点描述
    anomaly_details = []
    for a in anomalies[:5]:  # 最多展示前5个，避免消息过长
        idx = a["index"]  # 索引

        # 将异常点的 Unix 时间戳转换为 datetime 对象并格式化为[时:分:秒]
        ts = datetime.fromtimestamp(timestamps[idx]).strftime("%H:%M:%S")
        anomaly_details.append(f"- {ts} 延迟 {a['value']:.3f}s")
        # 列表推导式
        # anomaly_details = [f"- {datetime.fromtimestamp(timestamps[a['index']]).strftime('%H:%M:%S')} 延迟 {a['value']:.3f}s"for a in anomalies[:5]]

    message = {
        "msgtype": "markdown",  # 指定消息类型为 Markdown
        "markdown": {
            "title": "⚠️ API 延迟异常告警",  # 消息标题
            # 正文
            "text": f"### ⚠️ API 延迟异常告警\n\n"
                    f"**检测时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"**异常点数**：{len(anomalies)} 个\n\n"
                    f"**异常详情**：\n" + "\n".join(anomaly_details) +
                    f"\n\n> [查看 Grafana 面板](http://ubt1:3000)"
        }
    }

    # 发送 POST 请求到钉钉机器人 Webhook 地址，把告警消息推送到钉钉群
    resp = requests.post(url, json=message, timeout=10)
    if resp.status_code == 200:
        print("[INFO] 钉钉告警发送成功")
    else:
        print(f"[ERROR] 钉钉告警发送失败: {resp.text}")

# ========== 主流程 ==========
def main():
    if len(sys.argv) > 1:
        minutes = int(sys.argv[1])
    else:
        minutes = 30   # 默认 30 分钟
    print(f"\n{'=' * 50}")
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始执行巡检...")

    # 调用 Prometheus 接口拉取 Prometheus 数据
    values, timestamps = fetch_from_prometheus(minutes)
    print(values)
    print(timestamps)
    if values is None:
        return
    # 调用异常检测接口
    anomalies = detect_anomalies(values)

    # 发送钉钉告警
    send_dingtalk_alert(anomalies, timestamps)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 巡检完成\n")


if __name__ == "__main__":
    main()
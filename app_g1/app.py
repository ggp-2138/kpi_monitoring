from flask import Flask
from prometheus_client import Counter, Histogram, generate_latest
import time
import random

#创建 Flask 应用实例
app = Flask(__name__)       #app:全局 Web 应用对象，用于后续注册路由、启动服务

# 定义指标：请求计数和延迟直方图
#函数内分别是(指标名称,指标描述,标签) | method: 请求方式;endpoint: 访问的接口

# Counter: 计算器指标
REQUEST_COUNT = Counter('http_requests_total', 'Total requests', ['method', 'endpoint'])

# Histogram: 直方图指标
API_LATENCY = Histogram('api_latency_seconds', 'API latency', ['endpoint'])

#业务接口: /api 路由

@app.route('/api')     #路由装饰器:把下方 api() 函数绑定到 /api (默认只支持 GET请求)
#接口处理函数,访问 /api 时自动执行(其他同理)
def api():
    #给 REQUEST_COUNT 绑定标签值,每访问一次 /api 则记录一次 GET 请求,计数器 + 1
    REQUEST_COUNT.labels(method='GET', endpoint='/api').inc()
    # 模拟响应延迟：正常在 0.05~0.2 秒，偶尔飙到 1~2 秒
    #[随机数x]*n:生成n个随机数
    latency = random.choice([random.uniform(0.05, 0.2)]*90 + [random.uniform(1, 2)]*10)
    time.sleep(latency)         #阻塞线程 latency 秒，模拟接口业务处理耗时
    #调用.observe(数值):本次接口耗时录入直方图，Prometheus 自动统计延迟分布
    API_LATENCY.labels(endpoint='/api').observe(latency)
    return {'status': 'ok', 'latency': latency}

#Prometheus 指标暴露接口: /metrics

@app.route('/metrics')      #路由 /metrics,Prometheus 服务定时拉取该接口采集监控数据

def metrics():
    #generate_latest():读取所有指标，输出 Prometheus 标准文本格式
    #200：HTTP 200 成功状态码
    #Content-Type:固定 text/plain，Prometheus 只能识别该类型指标数据
    return generate_latest(), 200, {'Content-Type': 'text/plain; version=0.0.4'}

#程序入口，启动服务
if __name__ == '__main__':
    #启动 Flask 内置开发服务器
    #host='0.0.0.0':监听本机所有网卡 IP,允许局域网/外部机器访问
    #Flask 程序监听容器内的 8080 端口
    app.run(host='0.0.0.0', port=8080)
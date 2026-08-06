# 双轨可观测性智能告警平台

## 目录
1. [项目简介](#1-项目简介)
2. [系统架构](#2-系统架构)
3. [项目目录结构](#3-项目目录结构)
4. [部署步骤](#4-部署步骤)
5. [内置告警规则说明](#5-内置告警规则说明)
6. [智能异常检测（自定义 API 延迟）](#6-智能异常检测自定义-api-延迟)
7. [异常模拟复现](#7-异常模拟复现)
8. [配置修改规范](#8-配置修改规范)
9. [踩坑排错手册](#9-踩坑排错手册)
10. [后续拓展优化方向](#10-后续拓展优化方向)


## 1. 项目简介
基于 **Docker Compose** 一键部署 **Prometheus** + 多**Exporter** + **Alertmanager** + 钉钉告警中转服务，实现宿主机、**Nginx**、 **MySQL** 指标采集与告警推送；额外封装 **FastAPI MAD** 统计算法，实现应用 **API** 延迟智能异常检测，双告警链路覆盖固定阈值+时序离群检测

Demo视频：`bilibili.com/video/BV1Qe3M63EoX`

### 核心功能
- **多维度指标采集**：宿主机**CPU**/内存/磁盘、**MySQL**慢查询、**Nginx** 采集器运行状态、自定义业务接口延迟直方图
- **标准阈值告警链路**：**Prometheus**规则评估 → **Alertmanager** → **dingtalk-webhook**: 故障 **FIRING**、恢复 **RESOLVED** 消息双推送
- **智能时序异常检测**：基于 **FastAPI** 封装的 **MAD** 统计检测服务，定时从 **Prometheus** 拉取延迟数据，发现异常推送钉钉
- **容器化一键交付**：全组件Docker隔离，一条命令启停，无复杂本地环境依赖

## 2. 系统架构
### 数据流转链路架构图
```
┌────────────────────────────────────────────────────────────────────────────┐
│                                数据采集层                                   │
│ Node Exporter │ MySQL Exporter │ Nginx Exporter │ Demo App(app_g1)         │
│     采集主机、数据库、Web服务、自定义业务接口时序指标                         |                                                 
└───────────────────────────────────┬────────────────────────────────────────┘
                                    |
                                    | 原始指标数据
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                          存储与规则层 Prometheus                            │
│              时序指标存储 + 阈值告警规则评估 + HTTP查询接口                  │
────────────┬────────────────——──────── ─┬───────────────——─────────┬─────——┘ 
            │ 数据源                     │ 规则触发                  │ API 查询             
            ▼                            |                          |
         可视化层                        ▼   <-----告警处理层----->  ▼                   
┌───────————————————————┐         ┌──────────────┐          ┌──────────────────┐                      
|       Grafana         |         │ Alertmanager │          │  scheduler.py    |
|    主机/MySQL/Nginx   |         | 告警路由/分组 |          │  定时拉取指标     |                         
|   多维度可视化监控大盘 |         │              |          |                  |
└───────————————————————┘         └──────┬───────┘          └─────┬─────────▲──┘
                                         │ 转发                   │调用     |返回异常点
                                         ▼                        ▼         |
                              ┌──────────────────┐         ┌──────────────────────┐
                              │dingtalk-webhook  │         │   anomaly_service    │ <---- 智能检测层
                              │钉钉模板渲染+加签  │         │  MAD 时序异常检测 API │  
                              └────────┬─────────┘         └──────────┬───────────┘
                                   ▲   │                              │
                                   |   └──────────────┬───────────────┘ 
                                   |                  |
                                通知分发层             | 统一钉钉消息推送
                                        |              ▼
                                       ┌▼──────────────────────────────┐
                                       │          钉钉群               |
                                       |故障告警/恢复通知/性能异常告警  │
                                       └──────────────────────────────┘
```

### 架构说明
**1. 数据采集层**

负责全维度指标采集，对应各类 Exporter 与 Demo 业务应用：
- **Node-exporter**：宿主机 CPU、内存、磁盘系统指标
- **Mysql-exporter**：MySQL 连接、慢查询指标
- **Nginx-exporter**：Nginx 连接、请求总量指标（原生 stub_status）
- **Demo App(app_g1)**：自定义业务，暴露 API 延迟直方图指标

**2. 时序存储与告警规则层（Prometheus）**
- 定时抓取所有采集端指标，持久化时序数据
- 加载 alerts.yml 告警规则，持续计算 PromQL 表达式
- 指标异常时生成 FIRING 告警，指标恢复稳定 5 min 后生成 RESOLVED 恢复事件
- 对外提供 HTTP 查询接口，供定时脚本拉取历史延迟数据

**3. 告警处理层**

**分支 A：固定阈值告警链路（标准监控）**

Prometheus → Alertmanager → dingtalk-webhook → 钉钉群
- Alertmanager 配置send_resolved: true，同时推送故障、恢复通知
- 支持告警分组、自定义恢复等待时长resolve_timeout
- dingtalk-webhook 统一渲染 Markdown 钉钉消息模板

**分支 B：MAD 智能离群检测链路（业务性能专属）**

Prometheus → scheduler.py 定时拉取指标 → anomaly_service (FastAPI) → 钉钉群
- 独立于固定阈值，采用中位数绝对偏差算法识别突增高延迟
- 不依赖 Prometheus 告警规则，专门解决业务接口性能波动场景
- 支持手动单次检测 + crontab 定时自动巡检两种模式

**4.通知分发层**

两条告警分支统一推送至钉钉群，运维人员一站式接收硬件资源告警、数据库告警、采集器失联、业务接口性能异常、告警恢复全类型通知

**5. 可视化扩展层（Grafana）**

对接 Prometheus 数据源，导入官方标准化大盘，可视化展示 CPU、内存、磁盘、慢请求、请求量曲线，直观观测指标长期变化趋势

### 3. 项目目录结构
```
kpi_monitoring/
|
├── docker-compose.yml      # 容器编排主配置
|
├── prometheus.yml          # Prometheus 抓取配置
|
├── alerts.yml              # 告警规则定义
|
├── alertmanager.yml        # 告警路由
|
├── nginx.conf              # Nginx stub_status 指标暴露配置
|
├── mysql-exporter.cnf      # MySQL Exporter 连接凭证
|
├── dingtalk.yml            # 钉钉中转模板与签名
|
├── app_g1/                 # Demo 业务应用（暴露 /metrics）
|     |
│     ├── Dockerfile
|     |
│     ├── requirements.txt
|     |
│     └── app.py
|
├── anomaly_service.py      # FastAPI MAD 异常检测接口
|
├── scheduler.py            # 智能巡检调度脚本
|
├── week1_data_pull.py      # 历史指标数据拉取测试脚本
|
├── logs/                   # 运行日志目录
|
|── dashboard_json          #仪表板json文件
|
|── run_scheduler.sh        #定时脚本
|
|── stress_test.sh          #压力测试脚本
|
└── README.md                 
```

## 4. 部署步骤
### 4.1 准备工作(以下方法任选)
如果 **Docker Hub** 访问缓慢，可配置国内镜像加速或代理
### 配置镜像源
```bash
#执行命令
sudo vim /etc/docker/daemon.json
```
```json
#写入配置
{
  "registry-mirrors": [
    "https://docker.xuanyuan.me",
    "https://docker.mirrors.ustc.edu.cn",
    "https://docker.m.daocloud.io",
    "https://docker.1ms.run"          
  ]
}
```

### 配置代理
```bash
#执行命令
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo vim /etc/systemd/system/docker.service.d/http-proxy.conf
```
```bash
#写入配置
[Service]
Environment="HTTP_PROXY=http://你的代理地址:端口"
Environment="HTTPS_PROXY=http://你的代理地址:端口"
Environment="NO_PROXY=localhost,127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0.0/16"
```

### 重载并重启 Docker
```bash
sudo systemctl daemon-reload
sudo systemctl restart docker
```

### 验证镜像源和代理是否生效
```bash
# -E : 开启正则表达式
docker info | grep -inA5 -E "proxy|Registry Mirrors"
```
### 4.2 正式部署
### 克隆项目
```bash
git clone ggp-2138/kpi_monitoring
cd kpi_monitoring
```
### 修改配置文件
- **dingtalk.yml**：填写你的钉钉机器人 `webhook` 地址和加签密钥
- **prometheus.yml**：`node` 任务的 `targets` 需改为宿主机实际 IP（如 `192.168.112.xxx:9100`），其余可保持容器名
- **alertmanager.yml**：确认 `send_resolved: true` 已开启告警恢复通知
- **mysql-exporter.cnf**：密码与 `docker-compose.yml` 中 `MYSQL_ROOT_PASSWORD` 保持一致

### 各组件访问地址
- **Prometheus** 监控面板：**http://宿主机IP:9090**
- **Alertmanager** 告警面板：**http://宿主机IP:9093**
- **Grafana** 可视化：**http://宿主机IP:3000** (初始账号：**admin**, 密码：**admin** )


### 一键启动所有服务
```bash
#在 docker-compose.yml 所在目录下执行
docker compose up -d
```

### 检查数据链路
- 注意 **localhost**是一键启动所有容器的宿主机IP地址
- 浏览器打开 **http://localhost:9090/targets** ，确认所有 `targets` 状态为 **UP**；出现 **DOWN** 则排查端口、容器网络互通问题

### Grafana 可视化
- 打开 **Grafana** **http://localhost:3000** ，导入 **Node、MySQL、Nginx** 的仪表盘（ID **1860**、**7362**、**11199** | 仪表板 json 文件详见 `dashboard_json`），确认能看到数据

## 5. 内置告警规则说明
| 告警名称 | 监控对象 | 触发阈值 | 持续时长 | 告警级别 | 业务说明 |
| ---- | ---- | ---- | ---- | ---- | ---- |
| **HighCPU** | 宿主机 CPU | 使用率 > 80% | 1min | critical | 服务器 CPU 持续高负载 |
| **HostHighMemoryUsage** | 宿主机内存 | 使用率 > 85% | 1min | warning | 内存占用偏高 |
| **HostMemoryLow** | 宿主机内存 | 可用内存 < 5% | 1min | critical | 内存即将耗尽 |
| **HostDiskHighUsage** | 宿主机根磁盘 | 使用率 > 80% | 1min | warning | 根分区磁盘空间告急 |
| **MySQLSlowQueries** | MySQL 数据库 | 5 分钟新增慢查询 > 0 | - | warning | 数据库出现慢 SQL |
| **NginxDown** | Nginx 采集器 | exporter 离线 | - | critical | Nginx 指标采集中断 |
---
**注**：数值格式化（如四舍五入）已在 PromQL 表达式内完成，`annotation` 中直接引用 `$value`，避免模板引擎报错。

## 6. 智能异常检测（自定义 API 延迟）
本系统额外集成了一套统计异常检测服务，用于监控 Demo 应用的 API 延迟。
- 算法：**MAD**（中位数绝对偏差），只检测向上偏离的高延迟异常
- 服务：**FastAPI** 接口 **POST /detect**，接收延迟值列表，返回异常点索引和值
- 调度：`scheduler.py` 定时从 **Prometheus** 拉取过去 **30** 分钟的 **api_latency_seconds** 指标，调用 **/detect**，若发现异常则通过钉钉加签机器人推送告警

### FastAPI 服务启动

在终端**anomaly_service.py**文件所在目录下执行:
```bash
#需要先安装 uvicorn 库(pycharm直接搜 | pip install uvicorn)
# anomaly_service 是 Python 模块名
# app 是模块里创建的 FastAPI 实例对象
# --reload：开启热重载模式(生产环境禁止开启)
# --host 0.0.0.0: 监听本机所有网卡地址
# --port 8000: 指定服务监听端口为 8000
uvicorn anomaly_service:app --host 0.0.0.0 --port 8000
```
在宿主机终端执行,以下两种方法任选:
### 手动执行一次全量巡检
```bash
python scheduler.py
```

### 定时自动巡检
分别执行
```bash
crontab -e 
#每 5 分钟自动巡检
# /path/to 为绝对路径
*/5 * * * * cd /path/to/kpi_monitoring_2 && /path/to/python3 scheduler.py >> logs/scheduler.log 2>&1
```
### API 测试示例
### 方法一: 浏览器可视化测试
以下所有 **localhost** 是服务启动的主机地址
- 访问 **http://localhost:8000/docs** ,**FastAPI** 自动生成 **Swagger** 文档界面
- 点击 `POST /detect` → `Try it out` 
- 找到 `Request body` 例如输入：`{ "values": [0.1, 0.15, 0.2, 0.8, 0.12, 0.9]}`
- 点击 `Execute`，下方会显示服务器返回的 JSON

### 方法二: curl 命令测试
```bash
curl -X POST http:// FASTAPI 服务器 IP 地址:8000/detect \
-H "Content-Type:application/json" \
-H "Authorization: Bearer my-secret-token" \
-d '{"values":[0.1, 0.2, 0.3, 0.8, 0.9, 1.2]}'
```

### 方法三: 用 Python 脚本测试
```python
import requests
resp = requests.post("http://localhost:8000/detect", json={"values": [0.1, 0.15, 0.2, 0.8, 0.12, 0.9]})
print(resp.json())
```
- 运行 **Python 脚本**

### 验证方法
- 无论示例中的哪种方式，返回的 JSON 中 **anomalies** 列表应包含 0.8 和 0.9（因为它们是明显偏高的异常点）
- **示例输出**:
```json
{
  "anomalies": [
    {"index": 3, "value": 0.8},
    {"index": 5, "value": 0.9}
  ]
}
```

## 7. 异常模拟复现
### 1. Node CPU 高负载
在虚拟机安装 CPU 压力工具
```bash
# 安装 stress
sudo apt install stress -y

# 让 1 个 CPU 核心满载跑 3 分钟
stress --cpu 1 --timeout 180
```
**预期：**: 约 1 分钟后钉钉收到 **HighCPU** 告警；停止 **stress** 约 5 分钟后收到恢复通知,在 **Grafana** 仪表板看到 **CPU** 曲线陡升


### 2. Node 内存测试
```bash
# 开启2个进程，每个占用1G内存，持续120秒(示例，按需调整大小)
stress --vm 2 --vm-bytes 1G --timeout 120
```
**预期：**: 触发 **HostHighMemoryUsage** 或 **HostMemoryLow**,约 1 分钟后钉钉群收到告警

### 3. MySQL 慢查询
进入 **MySQL** 容器，执行一条超时的 SQL
```bash
# 进入容器执行慢查询SQL
docker exec -it mysql mysql -uroot -p12345 -e "SELECT SLEEP(10);"
```
**预期：**:**mysql_global_status_slow_queries** 的计数器增加，可以在 **Grafana** 仪表板看到慢查询数量上升

### 4. Nginx 请求量
用 curl 向 **Nginx** 发请求
```bash
# 简单循环发送 100 个请求
while true; do curl -s http://localhost:80/status > /dev/null; echo "Nginx 请求已发送";sleep 1; done
```
**预期：**: **nginx_http_requests_total** 数值增长，**Grafana** 曲线有变化，证明采集正常

### 5. Nginx 采集器失联
```bash
#1.停止 Nginx 采集器，等待约1分钟后触发 FIRING
docker stop nginx-exporte
#2.启动 Nginx 采集器
docker start nginx-exporter
```
**预期：**等待约 5 分钟后,钉钉群收到 **RESOLVED** 恢复通知

### 6. API 延迟异常检测测试(确保 FastAPI 服务已启动)
```bash
#每 0.5 秒访问一次 Demo 业务接口制造延迟指标
while true; do curl -s http://localhost:8080/api > /dev/null;echo "API 请求已发送";sleep 0.5; done
# 新开终端执行巡检脚本
python scheduler.py
```
**预期：**检测到异常延迟时，钉钉推送告警

## 8. 配置修改规范
### 热重载 Prometheus 配置（修改 alerts.yml 后）：
```bash
#project_name：项目名称（默认父目录名称）
docker kill -s SIGHUP project_name-prometheus-1
```
### 重启特定容器（修改 prometheus.yml 或 alertmanager.yml 后）：
```bash
docker container restart 容器名称
```
- **YAML** 语法：
- 缩进统一使用 2 个空格，禁止 Tab
- 确保多行字符串 | 的缩进正确
- **PromQL** 表达式：
- 避免顶层 **sum()** 导致 **instance** 标签丢失，多实例可使用 **sum by(instance) (...)**
- 数值格式化（**round** 等）写在 **expr** 中， **annotations** 模板内不支持管道函数
- 钉钉模板：`dingtalk.yml` 中的 **title**和 **text** 直接内联模板变量，模板内仅使用`$labels.xxx/$value`，不要使用未定义的函数

## 9. 踩坑排错手册
| 序号 | 故障现象 | 根本原因 | 完整解决方案 |
| ---- | ---- | ---- | ---- |
| 1 | **Prometheus** 加载规则报错 **function "round" not defined** | **annotations** 模板使用管道 **round**函数，模板引擎不支持 | 将 **round** 四舍五入迁移至 **expr** 表达式，模板仅读取 **$value** |
| 2 | 钉钉告警显示「实例：未指定」 | **PromQL** 顶层 **sum**() 聚合，清空 **instance** 标签；旧告警缓存无法修复 | 删除无必要 **sum**，多实例使用 **sum by (instance)**；仅新告警正常展示 **IP** |
| 3 | **NginxHighErrorRate**规则永久无告警 | 基础 **nginx-exporter** 基于**stub_status**，无 **HTTP** 状态码标签 | 删除该规则；如需错误率监控切换 **nginx-vts-exporter** |
| 4 | 故障恢复后钉钉长时间不推送 **RESOLVED** | **resolve_timeout** 默认为 5 分钟 | **alertmanager.yml** 调低至 2min，不建议低于 1min |
| 5 | 修改 **alerts.yml** 重载后规则不生效 | **YAML** 缩进 / 函数语法错误，**Prometheus** 保留旧规则集 | 执行 **docker logs** 查看 **Prometheus** 报错日志，修复后重载 |
| 6 | **Alertmanager** 日志 400 Bad Request | **dingtalk-webhook** 消息模板语法字段错误 | 检查 **dingtalk-webhook**（中转服务）日志，修正 **dingtalk.yml** 模板变量 |
| 7 | **MySQL** 慢查询持续 **FIRING** | **mysql-exporter** 周期性查询数据库，超过慢查询阈值 | 调高 **long_query_time**；给 **exporter** 账号关闭 **slow_query_log** |
| 8 | **dingtalk-webhook** 无容器无法访问外网（no route to host） | 容器默认 **bridge** ，**Docker 网桥SNAT** 规则缺失、转发异常 | 将 **dingtalk-webhook** 容器设置为 **network_mode:host**，在 **alertmanager.yml** 中将转发地址改为宿主机 **IP** |
---

## 10. 后续拓展优化方向
- 替换 Nginx-vts-exporter，实现 HTTP 状态码拆分和错误率指标采集与告警
- 配置 MySQL过滤规则，自动屏蔽 Exporter 采集类慢查询
- 扩展至多台宿主机/集群监控，新增 Prometheus 服务自动发现
- Alertmanager 配置：告警分组、抑制、定时静默，减少告警风暴

### 架构场景选型
**场景 1：小团队、单机部署**
- 运维、开发人员完全分开，不用配置 Alertmanager 复杂路由
- 追求简单、快速部署，不想维护多路由 
- 对告警降噪、统一复盘需求低

**场景 2：中大型集群,需要告警分级/复盘**

虽然配置繁琐，但长期运维收益更大：
- 多群只需要在 Alertmanager 新增一条路由，不用修改 Python 脚本
- 统一抑制、静默、恢复通知、历史告警，减少线上漏报、刷屏问题

**折中方案（兼顾分群优势 + 统一架构能力）**

如果既想要分开推不同钉钉群，又想复用 **Alertmanager** 能力：
- MAD 检测逻辑保留`scheduler.py`
- 检测到异常后调用 **Alertmanager** `/api/v1/alerts` 推送告警，打上标签 `group=biz_latency`

**Alertmanager 配置两套路由：**
- `group=resource` → 运维钉钉群
- `group=biz_latency` → 开发钉钉群
兼顾：多群分发、自动恢复、告警降噪、统一审计四大能力


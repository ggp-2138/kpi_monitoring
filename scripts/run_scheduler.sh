#!/bin/bash
MINUTES=${1:-30}
cd /home/hadoop/桌面/kpi_monitoring_3 || exit 1

# 方法一：使用 conda run（推荐，自动激活环境）
conda run -n aiops python scheduler.py "$MINUTES" >> logs/scheduler.log 2>&1

# 方法二：如果不用 conda，确保 python3 在 PATH 中
# python3 scheduler_param.py "$MINUTES" >> logs/scheduler.log 2>&1
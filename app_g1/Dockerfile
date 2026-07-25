FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .

# 使用国内镜像源，增加超时重试，避免下载中断
RUN pip install --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    --default-timeout=100 \
    -r requirements.txt


#分层复制加快镜像文件构建速度(对应文件哈希值改变才会重新执行命令)
COPY app.py .

#声明容器服务端口
EXPOSE 8080       

CMD ["python", "app.py"]
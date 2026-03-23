# ============================================
# 威科夫全自动逻辑引擎 - Docker 部署（多阶段构建）
# ============================================

# Stage 1: 前端构建
FROM node:18-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python 后端
FROM python:3.11-slim AS base

# 系统依赖（编译某些 Python 包可能需要）
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先复制依赖文件，利用 Docker 缓存层
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY src/ ./src/
COPY config.yaml run.py run_evolution.py fetch_data.py health_check.py ./

# 复制前端构建产物
COPY --from=frontend-build /app/frontend/dist ./frontend/dist/

# 创建数据和日志目录
RUN mkdir -p /app/data /app/logs /app/evolution_results /app/evolution_data /app/reports

# 暴露 API 端口
EXPOSE 9527

# 健康检查
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python health_check.py || exit 1

# 默认以 API 模式启动
CMD ["python", "run.py", "--mode=api"]

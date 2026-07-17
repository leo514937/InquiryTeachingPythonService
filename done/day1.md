# Day 1 - 项目骨架与初始化

## 分工

- 后端基础架构：FastAPI 入口、CORS、数据库、健康检查
- 引导脚本：`bootstrap.py`、`.env` 初始化、SQLite 建表
- 文档收口：启动方式、目录说明、最小可运行说明

## 目标

先把探究式教学助手的 Python 服务骨架稳定下来，让服务能启动、能建库、能健康检查。

## 开发任务

- 建立 FastAPI 入口、CORS、路由挂载和统一响应结构。
- 准备 SQLite 数据库和 ORM 基础表。
- 打通 `/health` 与 `bootstrap.py`。
- 准备基础环境说明，保证第一次运行不需要猜命令。

## 产物

- `app/main.py`
- `app/db/*`
- `bootstrap.py`
- `README.md`

## 验收标准

- `python bootstrap.py` 可完成 `.env` 初始化和 SQLite 建表。
- `GET /health` 返回正常状态。
- 启动后端不依赖登录流程。

## 当前状态

- 已完成并验证：启动、建库、健康检查。

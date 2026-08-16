# Design: Superset MCP Server 支持 Streamable HTTP 传输

日期：2026-08-16
状态：已确认

## 背景

superset-mcp 目前仅支持 stdio 传输（`main.py` 中 `main()` 调用 `mcp.run()` 默认 stdio）。
需要支持 Streamable HTTP 传输，用于远程部署场景。认证仍走 MCP 工具层的 Superset
登录（`superset_auth_authenticate_user`），HTTP 传输层不额外鉴权。

## 架构

单一入口 `main.py`，通过 CLI 参数在两种传输模式间切换：

| 参数 | 取值 | 默认 |
|------|------|------|
| `--transport` | `stdio` / `streamable-http` | `stdio` |
| `--host` | 监听地址 | `127.0.0.1` |
| `--port` | 监听端口 | `8000` |

- `stdio` 模式：保持现有 `mcp.run()` 行为不变。
- `streamable-http` 模式：`app = mcp.streamable_http_app()` 获取 ASGI app，
  通过 `uvicorn.run(app, host=..., port=...)` 启动，端点固定在 `/mcp`。

两种模式共享同一个 FastMCP 实例、同一个 `SupersetContext` lifespan（启动时加载
已存 token 并校验）以及全部 60 个工具，业务逻辑零改动。

## 组件

- `main.py`：`main()` 增加 `argparse` 参数解析与传输分支；新增 `run_http()` 函数
  负责 streamable-http 启动。

## 数据流

客户端 → HTTP POST `http://host:port/mcp`（JSON-RPC）→ FastMCP 处理 → 工具调用
Superset REST API。与 stdio 模式完全一致的请求处理路径，仅传输层不同。

## 错误处理

- uvicorn 启动失败（如端口占用）→ 捕获异常，打印明确错误信息，以非零码退出。
- 非法参数由 argparse 处理并输出用法。

## 测试

1. `python main.py --help` 验证参数定义。
2. stdio 回归：JSON-RPC 握手（initialize → tools/list），确认 60 个工具。
3. streamable-http 实测：启动 server → curl POST `/mcp` 依次发送
   initialize、tools/list、authenticate、dashboard_list → 验证响应 → 关闭 server。

## 文档

README 增加 "HTTP 模式" 小节，说明启动命令与 opencode/Claude 等客户端
remote 配置示例。

## 非目标

- HTTP 层鉴权（用户明确不需要）。
- Dockerfile / smithery.yaml 调整（不在本次范围）。
- mcp 2.0 迁移。

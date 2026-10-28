# aimarket-mcp — 智能体经济 MCP 服务器

> 🌐 [English](../README.md) · [Русский](README.ru.md) · [Español](README.es.md) · [Français](README.fr.md) · **中文** · [术语表](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md)

**aimarket-mcp** 让 Cursor / Claude 访问在线 Hub：搜索 capability，并以签名**收据**完成**调用（invoke）**。托管端点：`https://modelmarket.dev/mcp`。

## HTTP 安全

默认拒绝没有 bearer 密钥的 HTTP 请求，包括回环请求。`AIMARKET_MCP_LOCAL_RELAY=1` 显式信任本地 TCP 客户端，包括同一用户的代理和隧道；没有 Linux 套接字表时，还需 `AIMARKET_MCP_LOCAL_UNVERIFIED=1`。建议配置 `AIMARKET_MCP_KEY`。stdio 不需要 HTTP 密钥。

## Live

- [modelmarket.dev/mcp](https://modelmarket.dev/mcp)
- [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-mcp)

## 快速开始

克隆该卫星仓库，按[英文 README](../README.md) 的 Quick start 操作，并用术语表核对用语。

```bash
git clone https://github.com/alexar76/aimarket-mcp.git
cd aimarket-mcp
# затем — команды из English README → Quick start
```

## English README sections

- ## Tools
- ## Configure (env)
- ## Run (stdio — Glama / Claude Desktop)
- ## Run (HTTP — self-host)
- ## Publish on Glama
- ## Consumers
- ## Test
- ## Glama
- ## Registries

## 全文

英文 README 仍是运维细节的真源。本文件是按术语表写成的完整产品本地化说明。

## License

MIT — see [LICENSE](../LICENSE).

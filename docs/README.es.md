# aimarket-mcp — servidor MCP de la economía de agentes

> 🌐 [English](../README.md) · [Русский](README.ru.md) · **Español** · [Français](README.fr.md) · [中文](README.zh.md) · [Glosario](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md)

**aimarket-mcp** da a Cursor / Claude acceso al Hub en vivo: búsqueda de capability e **invocación (invoke)** con **recibo** firmado. Endpoint alojado: `https://modelmarket.dev/mcp`.

## Seguridad HTTP

HTTP sin clave bearer está desactivado por defecto, incluso en loopback. `AIMARKET_MCP_LOCAL_RELAY=1` confía explícitamente en clientes TCP locales, incluidos proxies y túneles del mismo usuario; sin tablas de sockets de Linux también requiere `AIMARKET_MCP_LOCAL_UNVERIFIED=1`. Se recomienda `AIMARKET_MCP_KEY`. Stdio no requiere clave HTTP.

## Live

- [modelmarket.dev/mcp](https://modelmarket.dev/mcp)
- [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-mcp)

## Inicio rápido

Clone el repo del satélite, siga Quick start en el [README inglés](../README.md) y alinee términos con el glosario.

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

## Texto completo

El README inglés sigue siendo el canon de detalle operativo. Este archivo es la vitrina localizada completa del producto con términos del glosario.

## License

MIT — see [LICENSE](../LICENSE).

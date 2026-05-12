<div align="center">

# 🌉 BriefBridge

**Handoff entre agentes — continue seu trabalho em qualquer ferramenta de IA sem perder o contexto.**

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-green)](LICENSE)
[![Testes](https://img.shields.io/badge/testes-142%20passando-brightgreen)](https://github.com/TiagoSchr/briefbridge)
[![PyPI](https://img.shields.io/badge/instalar-pip%20install%20briefbridge-orange?logo=pypi&logoColor=white)](https://github.com/TiagoSchr/briefbridge)

*Read in [English](README.md)*

</div>

---

O BriefBridge lê os dados de sessão locais do **GitHub Copilot Chat**, **Claude Code** e **Codex**, extrai contexto estruturado — objetivos, arquivos editados, erros, decisões, pendências — e gera um bloco pronto para colar em qualquer outra ferramenta.

**Todos os clientes usam o mesmo backend MCP. Só a interface muda.**

```
$ bb use claude:62003fff --mode compact

## BriefBridge Handoff
Objective: Fix JWT validation bug in the auth service.
Hypothesis: Token expiry check uses local timezone instead of UTC.
Files: src/auth.py (edited), tests/test_auth.py (edited)
Errors: AssertionError: token expired — from pytest
Pending: Add integration test for refresh tokens
```

> Cole esse bloco no início da próxima mensagem e você volta ao trabalho imediatamente.

---

## Índice

- [Por que isso existe?](#por-que-isso-existe)
- [Arquitetura](#arquitetura)
- [Instalação](#instalação)
- [GitHub Copilot](#github-copilot)
- [Claude Code](#claude-code)
- [Codex](#codex)
- [Referência da CLI](#referência-da-cli)
- [Ferramentas MCP](#ferramentas-mcp)
- [Desenvolvimento](#desenvolvimento)

---

## Por que isso existe?

Quando você troca de ferramenta de IA no meio de uma tarefa, perde todo o contexto. Precisa re-explicar o objetivo, re-listar os arquivos alterados e re-descrever cada erro que encontrou. O BriefBridge automatiza essa transferência.

- 🔍 **Lê** os arquivos de sessão locais de cada ferramenta (sem chamadas de API, nada sai da sua máquina)
- 🧠 **Extrai** objetivo, hipótese, arquivos, erros, comandos, decisões e pendências
- 📦 **Empacota** tudo em um bloco de handoff estruturado em segundos
- 🔌 **Funciona** como CLI, extensão do VS Code ou servidor MCP — escolha o que faz sentido para você

---

## Arquitetura

```
┌─────────────────────────────────────────────────────┐
│                   bb-mcp  (STDIO)                   │
│  bb_sessions_list    bb_session_inspect             │
│  bb_session_pack     bb_session_use                 │
│  bb_session_search                                  │
└──────────────────────┬──────────────────────────────┘
                       │
           ┌───────────▼───────────┐
           │   núcleo briefbridge  │
           │  adapters / extract   │
           │  storage  / render    │
           └───────────┬───────────┘
              ▲        ▲        ▲
         ~/.claude/  ~/.codex/  workspaceStorage/
```

```
src/briefbridge/
├── cli.py                # CLI Typer  ─  bb, briefbridge, bb-mcp
├── mcp_server.py         # Servidor FastMCP  ─  5 ferramentas via STDIO
├── config.py             # Detecção de caminhos por plataforma
├── adapters/             # Um adapter por provedor
│   ├── claude.py         # Lê ~/.claude/
│   ├── codex.py          # Lê ~/.codex/
│   └── copilot.py        # Lê workspaceStorage do VS Code
├── extract/
│   ├── deterministic.py  # Arquivos, erros, comandos, repositório
│   └── heuristic.py      # Objetivo, hipótese, decisões, TODOs
├── ingest/               # Orquestra adapter → extract → pack
├── models/               # Modelos Pydantic v2 (HandoffPack, RawSession…)
├── render/               # Saída JSON, Markdown, texto simples
├── services/             # Lógica de sessões, handoff, busca
├── storage/              # Cache SQLite FTS5
└── wrappers/             # Helpers de instalação por cliente
    ├── claude.py         # Comandos slash /bb:*
    ├── codex.py          # Skill $briefbridge
    └── copilot.py        # Helper de config MCP
```

---

## Instalação

**Requisitos:** Python 3.12+

```bash
git clone https://github.com/TiagoSchr/briefbridge.git
cd briefbridge
pip install -e .
```

Verificar:

```bash
bb --help
bb sessions
```

---

## GitHub Copilot

O BriefBridge inclui uma extensão do VS Code com o participante de chat `@bb`.

### Opção A — Extensão do VS Code *(recomendado)*

Compile e instale a extensão a partir do código-fonte:

```bash
cd vscode-ext
npm install
npm run package          # gera briefbridge.vsix
code --install-extension briefbridge.vsix
```

Reinicie o VS Code e use no Copilot Chat:

```
@bb /sessions
@bb /sessions claude          # filtrar por provedor
@bb /inspect <session_id>
@bb /use     <session_id>
@bb /pack    <session_id>
```

### Opção B — Backend MCP *(experimental)*

> Requer VS Code com GitHub Copilot Chat e suporte experimental a MCP habilitado.

**Passo 1 —** Execute o helper de instalação:

```bash
bb wrapper install --client copilot
```

Isso escreve o bloco correto no `settings.json` do VS Code:

```json
{
  "github.copilot.chat.experimental.mcp": {
    "servers": {
      "briefbridge": {
        "command": "bb-mcp",
        "args": [],
        "type": "stdio"
      }
    }
  }
}
```

**Passo 2 —** Reinicie o VS Code. O Copilot Chat terá acesso a todas as 5 ferramentas do BriefBridge.

---

## Claude Code

### Passo 1 — Instalar comandos slash

```bash
bb wrapper install --client claude
```

Isso cria `~/.claude/commands/bb/` com `sessions.md`, `inspect.md`, `pack.md`, `use.md`, `search.md`.

Reinicie o Claude Code e use:

```
/bb:sessions
/bb:inspect <session_id>
/bb:pack    <session_id>
/bb:use     <session_id>
/bb:search  <consulta>
```

### Passo 2 — Adicionar servidor MCP *(opcional, mas recomendado)*

Adicione em `~/.claude.json`:

```json
{
  "mcpServers": {
    "briefbridge": {
      "command": "bb-mcp",
      "args": [],
      "env": {}
    }
  }
}
```

Com o MCP configurado, o Claude Code chama as ferramentas diretamente — sem precisar executar comandos shell.

---

## Codex

### Passo 1 — Instalar a skill

```bash
bb wrapper install --client codex
```

Isso cria a skill `briefbridge` em `~/.agents/skills/briefbridge/SKILL.md`.

Reinicie o Codex. Digite `$briefbridge` no compositor para ativá-la, ou pergunte sobre sessões naturalmente — o Codex ativará a skill automaticamente.

### Passo 2 — Adicionar servidor MCP *(opcional, mas recomendado)*

Adicione em `~/.codex/config.toml`:

```toml
[mcp_servers.briefbridge]
command = "bb-mcp"
args    = []
```

Com o MCP configurado, o Codex chama as ferramentas diretamente em vez de executar comandos shell.

---

## Referência da CLI

```bash
# Listar sessões
bb sessions                           # todas as sessões recentes
bb sessions --last 24h                # últimas 24 horas
bb sessions --last 7d                 # últimos 7 dias
bb sessions --provider claude         # filtro: copilot | claude | codex
bb sessions --repo auto               # filtrar pelo repositório git atual
bb sessions --json                    # saída JSON

# Inspecionar uma sessão
bb inspect <session_id>
bb inspect <session_id> --json

# Gerar pacote de handoff
bb pack <session_id>
bb pack <session_id> --json

# Bloco de contexto pronto para colar
bb use <session_id>                           # compacto (padrão)
bb use <session_id> --mode full               # tudo
bb use <session_id> --mode goal,files,errors  # combinar seções

# Exportar para arquivo
bb export <session_id> --format json
bb export <session_id> --format md

# Buscar dentro de sessões
bb ask <session_id> "quais erros encontramos?"

# Instalar wrappers
bb wrapper install                    # todos os clientes
bb wrapper install --client claude
bb wrapper install --client codex
bb wrapper install --client copilot

# Iniciar servidor MCP
bb-mcp
```

### Modos de contexto para `bb use`

| Modo | O que você recebe |
|------|------------------|
| `summary` | Resumo em um parágrafo |
| `goal` | Só o objetivo |
| `hypothesis` | Só a hipótese principal |
| `files` | Arquivos alterados com funções inferidas |
| `errors` | Erros com trechos do log |
| `commands` | Comandos executados com códigos de saída |
| `decisions` | Decisões tomadas com nível de confiança |
| `todos` | Pendências com prioridade |
| `compact` | objetivo + hipótese + top arquivos + erros + pendências *(padrão)* |
| `full` | Tudo |

---

## Ferramentas MCP

O BriefBridge expõe **5 ferramentas** via protocolo MCP (transporte STDIO).  
Registre `bb-mcp` como servidor MCP em qualquer cliente compatível.

### `bb_sessions_list`

```json
Input:  { "hours": 24, "repo": "auto", "provider": "any" }
Output: { "sessions": [{ "id", "provider", "time", "repo", "files_count", "title", "status" }] }
```

### `bb_session_inspect`

```json
Input:  { "session_id": "copilot:abc123" }
Output: { "id", "provider", "repo", "branch", "objective", "main_hypothesis",
          "relevant_files", "errors_found", "important_commands",
          "decisions_made", "pending_items" }
```

### `bb_session_pack`

```json
Input:  { "session_id": "...", "mode": "compact" }
Output: { "handoff_id", "markdown", "plain_text", "json": { ... } }
```

### `bb_session_use`

```json
Input:  { "session_id": "...", "mode": "compact" }
Output: { "context_block": "string pronta para colar" }
```

### `bb_session_search`

```json
Input:  { "query": "bug JWT", "hours": 72, "provider": "any", "repo": null }
Output: { "matches": [{ "session_id", "provider", "score", "snippet" }] }
```

---

## Desenvolvimento

```bash
pip install -e ".[dev]"

# Rodar todos os testes
pytest tests/ -v

# Testes do servidor MCP
pytest tests/test_mcp_server.py -v

# Testes dos wrappers
pytest tests/test_wrappers/ -v
```

### Convenções do projeto

- Python 3.12+, Pydantic v2, Typer, Rich, FastMCP (SDK `mcp`)
- Sem chamadas a APIs externas — tudo é leitura de arquivos locais
- Adapters retornam resultados vazios/parciais quando dados do provedor não existem
- Todo output no terminal usa `sys.stdout.buffer` com UTF-8 explícito para compatibilidade no Windows

### Adicionando um novo provedor

1. Crie um adapter em `src/briefbridge/adapters/<provedor>.py` implementando `BaseAdapter`
2. Registre em `src/briefbridge/adapters/registry.py`
3. Adicione fixtures em `tests/fixtures/<provedor>/`
4. Adicione testes em `tests/test_adapters/test_<provedor>.py`

---

## Licença

MIT — veja [LICENSE](LICENSE).

---

<div align="center">

Feito com ☕ por [TiagoSchr](https://github.com/TiagoSchr)

</div>

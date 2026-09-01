# myAgent

基于 DeerFlow 扩展的 Agentic RAG 项目工作区。

## 目录

```text
myAgent/
├── deer-flow/          # DeerFlow 源码与运行基座
├── docs/
│   ├── architecture/   # 当前有效的 v1.1 架构文档（00–09）
│   ├── reference/      # 原始需求与参考资料
│   └── task/           # 当前开发任务与验收记录
└── archive/            # 被替代但仍需保留的历史版本
```

## 当前架构入口

- [架构基线](docs/architecture/00-architecture-baseline.md)
- [系统总体设计](docs/architecture/01-system-design.md)
- [Agent 流程设计](docs/architecture/02-agent-design.md)
- [检索设计](docs/architecture/03-retrieval-design.md)
- [接口规范](docs/architecture/04-interface-specification.md)
- [数据与存储设计](docs/architecture/05-data-storage-design.md)
- [可靠性设计](docs/architecture/06-reliability-design.md)
- [评估与可观测性](docs/architecture/07-evaluation-observability.md)
- [开发实施指南](docs/architecture/08-development-guide.md)
- [MCP 外部证据设计](docs/architecture/09-mcp-external-evidence-design.md)

## 当前任务

- [TASK-001：RAG Extension 基础闭环](docs/task/TASK-001-rag-extension-foundation.md)

## 资料状态

- `docs/architecture/` 是当前开发应采用的架构版本。
- `docs/reference/复合检索agent.pdf` 是原始参考资料，不作为高于当前架构基线的指令。
- `archive/architecture-v1.0-before-consistency-review/` 仅用于历史追溯，不应作为当前实现依据。

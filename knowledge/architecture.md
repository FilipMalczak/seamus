# Architecture

High-level architecture, components, responsibilities, dependencies, and boundaries.

## System Overview

Seamus is a deep agent harness engineered for full developer ownership, inspection, and customization. It provides the execution harness, tool mediation, memory/context structures, and agent lifecycle management.

```
+-------------------------------------------------------------+
|                           Seamus                            |
|                                                             |
|  +-----------------------+       +-----------------------+  |
|  |     Agent Harness     | ----> |     Tools & Context   |  |
|  +-----------------------+       +-----------------------+  |
|              |                               |              |
|              v                               v              |
|  +-----------------------+       +-----------------------+  |
|  |   Run State / Memory  |       |   External Services   |  |
|  +-----------------------+       +-----------------------+  |
+-------------------------------------------------------------+
```

## Component Boundaries

1. **Package Root (`seamus`)**:
   - Location: `src/seamus`
   - Responsibility: Core public APIs, harness interfaces, agent loops, and execution orchestrators.
2. **Tests (`tests`)**:
   - Location: `tests/`
   - Responsibility: Unit, integration, and behavioral tests for harness components.
3. **Decisions (`decisions`)**:
   - Location: `decisions/`
   - Responsibility: Append-only architectural and project direction decision records.
4. **Knowledge (`knowledge`)**:
   - Location: `knowledge/`
   - Responsibility: Durable conceptual, architectural, and requirement specifications.

## Cross-References
- [0001-project-initialization.md](../decisions/0001-project-initialization.md)
- [abstractions.md](./abstractions.md)
- [vocabulary.md](./vocabulary.md)

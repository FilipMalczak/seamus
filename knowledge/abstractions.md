# Abstractions

Interfaces, protocols, abstract base classes, implementations, package boundaries, and extension points.

## Package Boundaries

### `seamus` (`src/seamus`)
- The main package entry point.
- Exports public version `__version__`.
- All modules must be typed and covered by PEP 561 marker `py.typed`.

## Design Principles
- **Explicit over Implicit**: Prefer concrete, simple classes and protocols rather than speculative abstraction layers.
- **Separation of Concerns**: Keep framework/harness mechanics separate from application and agent domain code.
- **Type Annotations**: Public functions, methods, and classes must carry explicit type annotations.

## Cross-References
- [0001-project-initialization.md](../decisions/0001-project-initialization.md)
- [architecture.md](./architecture.md)
- [conventions.md](./conventions.md)

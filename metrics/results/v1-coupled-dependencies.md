# Dependências entre componentes: v1-coupled

```mermaid
graph LR
    c0["classification"]
    c1["config"]
    c2["extraction"]
    c3["llm"]
    c4["main"]
    c5["report"]
    c6["schemas"]
    c7["suggestion"]
    c8["tickets"]
    c0 --> c1
    c0 --> c3
    c0 --> c6
    c2 --> c1
    c2 --> c3
    c2 --> c6
    c3 --> c1
    c4 --> c0
    c4 --> c2
    c4 --> c5
    c4 --> c6
    c4 --> c7
    c5 --> c1
    c5 --> c3
    c5 --> c6
    c5 --> c8
    c7 --> c1
    c7 --> c3
    c7 --> c6
    c8 --> c1
    classDef dor fill:#ffcdd2,stroke:#c62828
    class c1,c3,c6 dor
```

Em vermelho, os componentes na zona de dor (A < 0,5, I < 0,5 e D ≥ 0,5).

## Ciclos

Nenhum ciclo de dependência.

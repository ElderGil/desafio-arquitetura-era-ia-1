# Dependências entre componentes: v2-decoupled

```mermaid
graph LR
    c0["adapters.gateway"]
    c1["adapters.tickets_file"]
    c2["classification"]
    c3["config"]
    c4["extraction"]
    c5["main"]
    c6["ports"]
    c7["report"]
    c8["schemas"]
    c9["suggestion"]
    c0 --> c6
    c1 --> c6
    c2 --> c6
    c2 --> c8
    c4 --> c6
    c4 --> c8
    c5 --> c0
    c5 --> c1
    c5 --> c2
    c5 --> c3
    c5 --> c4
    c5 --> c7
    c5 --> c8
    c5 --> c9
    c7 --> c6
    c7 --> c8
    c9 --> c6
    c9 --> c8
    classDef dor fill:#ffcdd2,stroke:#c62828
    class c3,c8 dor
```

Em vermelho, os componentes na zona de dor (A < 0,5, I < 0,5 e D ≥ 0,5).

## Ciclos

Nenhum ciclo de dependência.

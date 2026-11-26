---
bump: minor
refs: SPEC-0023
---
### Añadido
- `mth models` muestra también al planificador, fijo en `opus`; no sale de `[models]` y no se puede configurar.
- El agente planificador solo se lanza con `model: "opus"`: `mth-develop` lo exige y la plantilla de encargo de `mth-plan` declara «Modelo: opus». Si el encargo no lo indica, el agente avisa.

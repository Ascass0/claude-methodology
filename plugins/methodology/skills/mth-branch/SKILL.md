---
name: mth-branch
description: Crea ramas de trabajo (feat, fix, chore, hotfix, prefijos del repo, ramas hijas con --). Úsala al empezar un cambio, al dividir una feature o si estás en main o development y necesitas modificar algo.
---

# Ramas

`mth` es el comando del contexto de sesión (`$MTH`). Nunca crees ramas con `git checkout -b` directamente.

## Primer nivel

```
mth branch feat <slug> --plan PLAN-NNNN [--spec SPEC-NNNN] # desde development
mth branch fix <slug> --plan PLAN-NNNN [--spec SPEC-NNNN]  # desde development
mth branch chore <slug>                   # desde development
mth branch hotfix <slug> --plan PLAN-NNNN [--spec ...]     # desde main
mth branch <prefijo-extra> <slug>         # según [branches.extra]
```

`--plan` es obligatorio en los tipos de `plans.required_for` (por defecto `feat`, `fix` y `hotfix`): el plan debe estar `acordado` (skill `mth-plan`). La rama se registra en el plan, en `.work/plans/` (local). Sin plan acordado, `mth branch` no crea la rama; `mth integrate` y `mth hotfix finish` exigen además que la rama figure en un plan en curso.

Slug: minúsculas, dígitos y guiones (`ephemeral-runner`). Crea la rama sincronizada con su base, la sube al remoto y, para `feat`, `fix` y `hotfix`, crea el fragmento `changes/<tipo>-<slug>.md` que completarás antes de integrar. Si la spec de la feature aún no existe, créala en la rama con la skill `mth-spec`: se enlaza sola al fragmento.

## Ramas hijas

Desde la rama padre: `mth branch fix cleanup-timeout --child` → `feat/ephemeral-runner--fix-cleanup-timeout`.

Tipos: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`. Crea una hija solo si el trabajo es separable y justificable (un subproblema con entidad propia, un fix descubierto durante la feature). Las hijas no llevan fragmento ni revisión propia: se integran en su padre con `mth integrate` y se revisan como parte de ella.

## Reglas

- Una rama padre no se integra con hijas abiertas (`mth integrate` lo bloquea).
- Si la rama destino avanza, `mth sync` (merge, nunca rebase).

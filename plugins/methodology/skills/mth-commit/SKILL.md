---
name: mth-commit
description: Hace commits temáticos con mensaje Conventional Commits validado, cuerpo descriptivo y trailer Refs. Úsala cada vez que tengas un conjunto coherente de cambios listo para confirmar, en lugar de git commit; también para decidir cómo agrupar cambios en commits.
---

# Commits temáticos

`mth` es el comando del contexto de sesión (`$MTH`).

## Agrupar

1. `git status` y `git diff`: identifica los temas (una capacidad, un fix, un refactor, la documentación de una feature, sus tests).
2. Un commit por tema, con todo lo que pertenece a ese tema (código, tests y docs juntos si forman la misma unidad). No un commit por fichero ni un volcado de todo.
3. Cada commit deja los tests en verde.
4. Un commit atómico (un único cambio mínimo) solo si se justifica, y la justificación va en el cuerpo.

## Confirmar

```
git add <rutas del tema>
mth commit --type feat --scope runner \
  --summary "create and destroy one container per task" \
  --body "Each delegated task gets its own sandbox. Teardown runs on success, error, timeout and cancellation; the reaper removes leftovers by label." \
  --refs SPEC-NNNN,ADR-NNNN
```

- `--type`: feat, fix, refactor, perf, docs, test, build, ci, chore, revert.
- `--summary`: inglés, imperativo, sin punto final; la cabecera completa ≤ 72 caracteres.
- `--body` (o `--body-file`): inglés; qué cambia y por qué.
- `--refs`: obligatorio en feat, fix, refactor y perf (IDs definidos o issues `#123`); `n/a` en el resto si no aplica.
- `--breaking "<descripción>"` para cambios incompatibles.

El script valida el formato y que las referencias existan, ejecuta `commands.precommit` y hace el commit. El hook `commit-msg` aplica las mismas reglas a cualquier `git commit`.

## Si te equivocas

No reescribas historia compartida. Si el commit no se ha subido y el error es del mensaje, `git commit --amend` está permitido. Si ya se subió, añade un commit nuevo que corrija.

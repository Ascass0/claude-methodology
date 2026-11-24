---
name: mth-integrate
description: Integra la rama actual en su destino (hija en su padre, feature en development) por PR con merge commit tras los gates. Úsala con la rama terminada; nunca hagas merges, push a ramas protegidas ni gh pr merge a mano.
---

# Integración

`mth` es el comando del contexto de sesión (`$MTH`).

## Pasos

1. Árbol limpio, commits hechos (skill `mth-commit`).
2. `mth sync`. Si hay conflictos: resuélvelos, `git add`, `git commit --no-edit` y repite `mth sync`.
3. Rama de primer nivel: fragmento completo, spec en `implementada` (feat), revisión registrada (skill `mth-review`).
4. Integra:

```
mth integrate --title "feat(runner): ephemeral container per task" \
  --summary "Resumen en español: qué aporta la rama, decisiones relevantes y cómo se ha verificado."
```

- `--title`: cabecera Conventional Commits en inglés; será el asunto del merge commit.
- `--summary` (o `--summary-file`): español; abre la descripción del PR. Un resumen largo se escribe en `.work/merge-request/<rama>.md` y se pasa con `--summary-file`.

## Qué hace el script (en este orden; si algo falla, no se toca el remoto)

1. Comprueba que la rama contiene el último destino y que no tiene hijas abiertas.
2. Valida los mensajes de todos los commits de la rama.
3. Valida el fragmento de changelog (primer nivel).
4. `mth trace`.
5. Revisiones del HEAD actual sin bloqueantes (primer nivel).
6. Tests (`commands.test`).
7. Push, PR (o reutiliza el abierto), espera a la CI, merge commit con los commits y las referencias en el cuerpo, borra la rama y sincroniza el destino.

Es idempotente: si falla a mitad (CI en rojo, red), corrige y vuelve a ejecutarlo.

## Con `forge` = `gitlab` o `none`

`mth integrate` hace los mismos gates, sube la rama y deja el título y la descripción del MR en `.work/merge-request/<rama>.md`, pero **no fusiona** (no puede comprobar la CI) ni llama a `gh`. Termina con los pasos manuales: abrir el MR, esperar a la CI, fusionar con merge commit y volver a ejecutar el mismo `mth integrate`, que detecta el merge y limpia la rama. Muéstrale esos pasos a la persona tal cual y espera: no hagas el merge por otra vía (el guard bloquea `glab mr merge`).

## Hotfix

Una rama `hotfix/` de primer nivel no se integra: se publica con `mth hotfix finish` (skill `mth-release`).

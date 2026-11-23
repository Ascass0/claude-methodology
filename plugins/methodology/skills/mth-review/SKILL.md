---
name: mth-review
description: Ejecuta la revisión de la rama con los agentes revisores declarados en el repo, con contexto limpio, severidades y precedencia, y registra el resultado sobre el HEAD exacto. Úsala antes de integrar cualquier rama feat, fix o hotfix, y cada vez que haya commits nuevos después de una revisión.
---

# Revisión

`mth` es el comando del contexto de sesión (`$MTH`). Los revisores son `review.agents` en `.claude/methodology.toml`, en orden de precedencia. Algunos solo aplican si el diff toca sus rutas (`review.paths`): **`mth review status` dice cuáles son obligatorios para esta rama**. Lanza esos y ninguno más.

`verificador` (compartido, incluido en el plugin) comprueba que la rama cumple su spec y ejecuta los tests. Si está en la lista, va primero: no tiene sentido revisar estilo o parsimonia de algo que no cumple la spec.

Los revisores del catálogo (`revisor-seguridad`, `revisor-fallos`, `revisor-adr`, `revisor-diseno`, `revisor-parsimonia`) se instalan en `.claude/agents/` con `mth agents add`, que los coloca en `review.agents` según la precedencia de PRINCIPLES §0. Su guard solo les deja leer git: no les pidas otra cosa.

## Antes de revisar

1. `mth sync` (la revisión es sobre el HEAD que se va a integrar).
2. Lo determinista primero: tests, `commands.precommit`, `mth trace`. Un agente no revisa lo que una herramienta comprueba.

## Revisar

Lanza los revisores obligatorios **en el orden de `review.agents`**: el `verificador` primero y, si no hay bloqueantes, el resto como subagentes (herramienta Agent con su nombre y el modelo `models.review` que muestra `mth models`; los del plugin pueden aparecer con el prefijo `methodology:`), en paralelo si es posible. A cada uno, este encargo y nada más (contexto limpio: ni la conversación ni tu razonamiento):

```
Revisa la rama <rama> respecto a <destino>.
- Diff: git diff <remoto>/<destino>...HEAD
- Specs y ADR afectados: <IDs y rutas>
- Principios: <ruta de PRINCIPLES.md del contexto de sesión>
Aplica solo tu especialidad. Para cada hallazgo devuelve:
  severidad (bloqueante | importante | sugerencia) · fichero:línea · problema · corrección propuesta
Bloqueante = incumple una regla DEBE, un criterio de aceptación, o introduce un riesgo.
Termina con: BLOQUEANTES: <n>
```

Guarda el informe completo de cada revisor, tal cual, en `.work/reviews/<rama>-<agente>.md` (local, excluido de git). Su última línea es `BLOQUEANTES: <n>`.

**Revisor que no termina** (se cae, agota el tiempo o su informe no acaba en `BLOQUEANTES: <n>`): no ha revisado. Nunca cuenta como "sin hallazgos". Relánzalo una vez con el mismo encargo; si vuelve a fallar, detente y avisa (PRINCIPLES §11).

## Resolver

- Corrige los bloqueantes. Los importantes, salvo que contradigan una regla de mayor precedencia (seguridad > fail-safe/fail-fast > corrección > trazabilidad > parsimonia > estilo); las sugerencias, a criterio.
- Si dos revisores se contradicen, gana la precedencia; entre revisores, el que va antes en `review.agents`. Anota la decisión en el resumen.
- Tras corregir: commit (skill `mth-commit`) y **vuelve a revisar**: un commit nuevo invalida las revisiones anteriores.

## Registrar

Por cada agente, sobre el HEAD final:

```
mth review record <agente> --report <informe> --summary "<resumen en español en una línea>"
mth review status
```

`mth` toma los bloqueantes de la última línea del informe. Si el informe falta, está vacío o no termina en esa línea, no registra nada y la revisión sigue pendiente.

`mth integrate` exige un registro con 0 bloqueantes de cada revisor para el HEAD actual, y copia los resúmenes al PR.

---
name: mth-review
description: Ejecuta la revisión de la rama con los agentes revisores declarados en el repo, con contexto limpio, severidades y precedencia, y registra el resultado sobre el HEAD exacto. Úsala antes de integrar cualquier rama feat, fix o hotfix, y cada vez que haya commits nuevos después de una revisión.
---

# Revisión

`mth` es el comando del contexto de sesión (`$MTH`). Los revisores son `review.agents` en `.claude/methodology.toml`, en orden de precedencia. Algunos solo aplican si el diff toca sus rutas (`review.paths`): **`mth review status` dice cuáles son obligatorios para esta rama**. Lanza esos y ninguno más.

`verificador` (compartido, incluido en el plugin) comprueba que la rama cumple su spec y ejecuta los tests. Si está en la lista, va primero: no tiene sentido revisar estilo o parsimonia de algo que no cumple la spec.

## Antes de revisar

1. `mth sync` (la revisión es sobre el HEAD que se va a integrar).
2. Lo determinista primero: tests, `commands.precommit`, `mth trace`. Un agente no revisa lo que una herramienta comprueba.

## Revisar

Lanza el `verificador` primero y, si no hay bloqueantes, el resto de revisores obligatorios como subagentes (herramienta Task con su nombre; los del plugin pueden aparecer con el prefijo `methodology:`), en paralelo si es posible. A cada uno, este encargo y nada más (contexto limpio: ni la conversación ni tu razonamiento):

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

## Resolver

- Corrige los bloqueantes. Los importantes, salvo que contradigan una regla de mayor precedencia (seguridad > fail-safe/fail-fast > corrección > trazabilidad > parsimonia > estilo); las sugerencias, a criterio.
- Si dos revisores se contradicen, gana la precedencia. Anota la decisión en el resumen.
- Tras corregir: commit (skill `mth-commit`) y **vuelve a revisar**: un commit nuevo invalida las revisiones anteriores.

## Registrar

Por cada agente, sobre el HEAD final:

```
mth review record <agente> --blocking <n> --summary "<resumen en español en una línea>"
mth review status
```

`mth integrate` exige un registro con 0 bloqueantes de cada revisor para el HEAD actual, y copia los resúmenes al PR.

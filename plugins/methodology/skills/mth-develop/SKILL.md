---
name: mth-develop
description: Ciclo completo de desarrollo autónomo dirigido por specs de claude-methodology, de la spec a la versión publicada. Úsala siempre al empezar cualquier trabajo de desarrollo en un repo que tenga .claude/methodology.toml (implementar una feature, corregir un bug, mantenimiento, continuar una tarea a medias) y cuando dudes de qué paso toca a continuación.
---

# Ciclo de desarrollo

`mth` es el comando que aparece en el contexto de sesión (`sh …/scripts/mth`), también disponible como `$MTH`. Trabajas sin pedir permiso. Ejecuta `mth status` si no sabes en qué punto estás.

## 1. Clasifica el cambio (PRINCIPLES §12)

| Tipo | Rama | Spec | Fragmento | Revisión |
|---|---|---|---|---|
| Mantenimiento (docs, CI, deps sin cambio de comportamiento) | `chore/` | no | no | no |
| Bug | `fix/` | referencia la spec o el issue afectado | sí | sí |
| Comportamiento nuevo | `feat/` | **obligatoria** (se escribe en la rama) | sí | sí |
| Estructural | `feat/` o `chore/` | sí + **ADR aceptado antes de implementar** | sí | sí |
| Bug en producción (main) | `hotfix/` | referencia | sí (patch) | sí |

## 2. Rama → skill `mth-branch`

`mth branch feat <slug>` (añade `--spec SPEC-NNNN` si la spec ya existe). Para trabajo separable dentro de la feature, ramas hijas (`--child`), solo si se justifica.

## 3. Spec y decisiones → skill `mth-spec`

Si la spec no existe, escríbela en la propia rama como primer commit: contexto, objetivo, fuera de alcance, comportamiento, **modos de fallo** y **criterios de aceptación verificables**. Pásala a `aprobada` cuando sea coherente con los principios y los ADR vigentes. Toda decisión estructural va en un ADR aceptado antes de implementarla. `mth integrate` rechaza una feature cuyo fragmento no referencie su spec.

## 4. Implementa

Con los principios activos: Design for Failure, fail-safe/fail-fast, parsimonia, excepciones solo donde se actúa, trazas con ID de correlación, docstrings mínimos, referencias `ADR-NNNN` en decisiones no obvias. Delega en los agentes de rol del repo si `[roles]` los declara.

- Tests: uno por AC (con `verifies: SPEC-NNNN/AC-NN`), uno por modo de fallo, uno de regresión por bug. Ninguno más.
- Docs actualizadas en la misma rama.
- Commits temáticos durante el trabajo → skill `mth-commit`.

## 5. Cierra la rama

1. Completa el fragmento `changes/<tipo>-<slug>.md` (en español, orientado al usuario).
2. Feature: pon la spec en `implementada`.
3. `mth trace` sin hallazgos → skill `mth-trace`.
4. `mth sync` para traer la rama destino.
5. Revisión → skill `mth-review` (sobre el HEAD final).
6. Integración → skill `mth-integrate`.

## 6. Versión → skill `mth-release`

Cuando `development` reúne features completas y estables entre sí, publica. Los hotfix se cierran con `mth hotfix finish`.

## Cuándo parar (PRINCIPLES §11)

Solo si dos specs o principios se contradicen sin que la precedencia lo resuelva, si un gate falla tres veces por la misma causa, o si la tarea exige algo irreversible fuera de las specs. En cualquier otro caso: elige la opción más conservadora, documéntala y continúa.

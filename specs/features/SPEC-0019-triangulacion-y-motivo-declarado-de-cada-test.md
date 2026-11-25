# SPEC-0019 · Triangulación y motivo declarado de cada test

- Estado: aprobada
- Fecha: 2026-11-25
- Formato: compacto
- ADRs: [ADR-0015](../adr/process/ADR-0015-triangulacion-y-motivo-declarado-de-cada-test.md), [ADR-0014](../adr/process/ADR-0014-formato-compacto-de-specs-y-adr.md)
- Sustituye a: —

## Contexto

- Con un solo test por AC el agente puede escribir una solución fija para sus valores; nada detecta los tests de andamiaje que sobran.
- [ADR-0015](../adr/process/ADR-0015-triangulacion-y-motivo-declarado-de-cada-test.md) exige dos ejemplos de clases distintas por AC con entrada variable y una etiqueta por test.

## Objetivo

1. `mth trace` exige una etiqueta en cada test: un test nuevo sin ella bloquea `mth integrate`.
2. Los tests heredados de un repo adoptado (`trace.legacy_base`) solo avisan.
3. Triangulación, andamiaje y casos especiales entran en los principios, los revisores y el ciclo de `mth-develop`.

## Fuera de alcance

- Verificar el orden rojo → verde → refactor.
- Mutation testing.
- Decidir con script si dos tests son de la misma clase de equivalencia (criterio de `revisor-parsimonia`).
- Etiquetar los tests de `tests/test_mth.py`: sigue en `trace.exclude`.

## Comportamiento

### Etiquetas

| Etiqueta | Forma | Significa |
|---|---|---|
| `verifies:` | `SPEC-NNNN/AC-NN` o `SPEC-NNNN/FM-NN` | Verifica un criterio o un modo de fallo |
| `regression:` | cualquier referencia (issue, commit) | Falla sin el fix de un bug |
| `unit:` | símbolo público | Función pública con lógica no trivial |

- La etiqueta va en un comentario (o docstring) de la región del test: desde sus comentarios contiguos previos hasta la línea anterior al siguiente test.
- Una palabra de etiqueta con forma incorrecta (`verifies: pendiente`) no cuenta como etiqueta.

### Detección

- `trace.test_patterns`: tabla glob → regex de la línea que abre un test. Se superpone a los valores por defecto; un valor `""` desactiva el patrón de ese glob.

  | Glob | Regex por defecto |
  |---|---|
  | `**/*.py` | `^\s*(?:async\s+)?def\s+test\w*\s*\(` |
  | `**/*.js`, `**/*.jsx`, `**/*.mjs`, `**/*.cjs`, `**/*.ts`, `**/*.tsx` | `^\s*(?:it\|test)(?:\.\w+)*\s*\(` |
  | `**/*.go` | `^func\s+Test\w*\s*\(` |

- Se examinan los ficheros de `paths.tests` que `trace.include` / `trace.exclude` dejan pasar.
- Fichero sin patrón aplicable: si su nombre es de test (`test_*`, `*_test.*`, `*.test.*`, `*.spec.*`) y su extensión no es de datos (`.md`, `.json`, `.toml`, `.yaml`, `.yml`, `.txt`, `.csv`, `.snap`), debe llevar al menos una etiqueta.

### Avisos

- `mth trace` termina con `⚠ N criterios con un único test: mth trace --single los lista` cuando algún AC de una spec tiene un solo test que lo verifique. No cambia el código de salida ni bloquea.

### Legado

- Los hallazgos de etiquetas en ficheros legados (SPEC-0005) son avisos, como cualquier otro.

### Principios, revisores y ciclo

- PRINCIPLES §6: triangulación, etiqueta por test y eliminación del andamiaje.
- `revisor-parsimonia`: dos tests de la misma clase para el mismo AC (indica cuál sobra) y etiquetas que no dicen la verdad.
- `revisor-fallos`: casos especiales para los valores del test → bloqueante.
- `mth-develop`: ciclo de triangulación.
- Evals de ambos revisores actualizadas.

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | Lenguaje sin patrón | Comprobación por fichero | AC-05 |
| FM-02 | Regex de `trace.test_patterns` inválida | Error de configuración que nombra la clave; ningún comando corre | AC-01 |
| FM-03 | El patrón reconoce como test una línea que no lo es | Hallazgo con su línea; se ajusta el patrón o `trace.exclude` | AC-02 |
| FM-04 | Etiqueta con forma incorrecta | No cuenta: el test se reporta y el mensaje la nombra | AC-04 |
| FM-05 | `verifies:` apunta a un AC o FM que no existe | Hallazgo (comprobación existente de `mth trace`) | AC-03 |
| FM-06 | Repo adoptado con tests sin etiquetar | Con `trace.legacy_base` son avisos; sin él, errores | AC-06 |
| FM-07 | Fichero de tests ilegible o de más de 1 MB | No se comprueba, como el resto de `mth trace` | AC-02 |

## Criterios de aceptación

- **AC-01**: `trace.test_patterns` DEBE traer valores por defecto para Python, JS/TS y Go, y una regex inválida DEBE fallar la carga de la configuración nombrando la clave.
- **AC-02**: SI un test no lleva etiqueta, ENTONCES `mth trace` DEBE reportarlo como error con su fichero y su línea.
- **AC-03**: CUANDO un test lleva `verifies:` (AC o FM), `regression:` o `unit:` en su región, `mth trace` NO DEBE reportarlo.
- **AC-04**: SI una etiqueta tiene forma incorrecta, ENTONCES `mth trace` DEBE reportar el test nombrando la etiqueta.
- **AC-05**: MIENTRAS un fichero de tests no tenga patrón para su lenguaje, `mth trace` DEBE exigirle al menos una etiqueta.
- **AC-06**: SI el fichero es legado, ENTONCES el hallazgo de etiqueta DEBE ser un aviso que no bloquea.
- **AC-07**: CUANDO un test nuevo sin etiqueta llega a `mth integrate`, la integración DEBE rechazarse antes de tocar el remoto.
- **AC-08**: CUANDO un AC tiene un único test, `mth trace` DEBE avisar sin cambiar el código de salida, y `--single` DEBE listarlos.
- **AC-09**: PRINCIPLES §6, `mth-develop`, `revisor-parsimonia`, `revisor-fallos` y sus evals DEBEN recoger la triangulación, el andamiaje y los casos especiales.
- **AC-10**: Los tests del propio plugin DEBEN llevar etiqueta: `mth trace` sobre este repo no da hallazgos de etiquetas.

## Notas

- Cambio incompatible para repos adoptados con tests sin etiquetar; el fragmento lo marca y el CHANGELOG explica la migración.

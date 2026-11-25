# SPEC-0020 · Límite de líneas por fichero

- Estado: aprobada
- Fecha: 2026-11-25
- Formato: compacto
- ADRs: [ADR-0016](../adr/process/ADR-0016-limite-de-lineas-por-fichero.md)
- Sustituye a: —

## Contexto

- Un fichero grande cuesta contexto al agente y suele incumplir la responsabilidad única; hoy no hay límite.
- [ADR-0016](../adr/process/ADR-0016-limite-de-lineas-por-fichero.md) fija un límite con excepciones con techo y un trinquete sobre la rama.

## Objetivo

1. Un fichero de 3000 líneas que la rama toca sin hacerlo crecer solo avisa.
2. Hacerlo crecer, o crear uno por encima del límite, bloquea.
3. Las excepciones declaran techo y motivo, y caducan.

## Fuera de alcance

- Valorar el `reason` con script (lo hace `revisor-diseno`).
- Contar líneas lógicas o de código.
- Límites por tipo de fichero distintos del global.

## Comportamiento

### Configuración

| Clave | Por defecto | Significa |
|---|---|---|
| `limits.max_file_lines` | `1000` | Entero ≥ 1: líneas máximas por fichero |
| `limits.exclude` | `**/*.lock`, `**/package-lock.json`, `**/migrations/**`, `**/generated/**` | Globs de ficheros que no se miden; una lista propia sustituye a la de defecto |
| `limits.exceptions` | vacía | Tabla de excepciones |

- Excepción: `path` (glob, normalmente un fichero), `max_lines` (entero mayor que `max_file_lines`), `reason` (texto no vacío) y `refs` (opcional).
- Claves desconocidas o de tipo incorrecto en una excepción son un error de configuración que nombra la excepción.

### Medida

- Líneas físicas: saltos de línea más uno si la última línea no termina en salto; fichero vacío = 0.
- No se miden los ficheros con un byte NUL ni los que `git` marca como binarios (`diff` sin definir o `-diff` en `.gitattributes`), ni los de `limits.exclude`.

### Trinquete

- Base de comparación: el merge-base de la rama con su destino (`mth branch` calcula el destino: `development`, `main` en hotfix o la rama padre en hijas).
- Para cada fichero medido por encima del límite sin excepción:

  | Caso | Resultado |
  |---|---|
  | La rama lo crea por encima del límite, o lo hace pasar de ≤ límite a > límite | Error |
  | La rama lo hace crecer estando ya por encima | Error |
  | La rama lo toca sin hacerlo crecer, o no lo toca | Aviso |
  | No hay rama padre (`development`, `main`, ramas ajenas) | Aviso |

- Fichero con excepción: error si supera su `max_lines`; si no, sin hallazgo.
- Excepción caducada: error si ningún fichero medido que case con su `path` supera `max_file_lines`.
- Un renombrado que git detecta se compara con su ruta de origen.
- La base solo se calcula si algún fichero sin excepción supera el límite.

### Salida de `mth trace`

- Los errores salen como el resto de hallazgos (fichero:línea, bloquean `mth integrate` y los demás gates).
- Con avisos, `mth trace` termina con `⚠ N ficheros por encima del límite de líneas: mth trace --limits los lista`; `--limits` los lista. No cambia el código de salida.

### Principios y revisor

- PRINCIPLES §5 recoge la regla.
- `revisor-diseno` valora el `reason` de cada excepción nueva o ampliada; evals actualizadas.

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | Excepción sin `max_lines` o `reason`, o con `max_lines` no superior al límite | Error de configuración que nombra la excepción; ningún comando corre | AC-01 |
| FM-02 | La rama padre no se puede leer y hay ficheros largos que comparar | Error que nombra la causa y el remedio; no se relaja el límite | AC-08 |
| FM-03 | Fichero binario o con NUL | No se mide | AC-02 |
| FM-04 | Renombrado que git no detecta | Cuenta como fichero nuevo: error si supera el límite; se declara una excepción | AC-05 |
| FM-05 | Fichero muy grande | Se mide en bloques, sin cargarlo entero | AC-02 |
| FM-06 | Rama sin padre (`development`, `main`) | Solo avisos de tamaño; los errores de excepciones siguen aplicando | AC-07 |

## Criterios de aceptación

- **AC-01**: SI una excepción no declara `max_lines` y `reason`, o su `max_lines` no supera `max_file_lines`, o `max_file_lines` es menor que 1, ENTONCES la carga de la configuración DEBE fallar nombrando la excepción.
- **AC-02**: `mth trace` DEBE medir líneas físicas y NO DEBE medir ficheros con un byte NUL.
- **AC-03**: `mth trace` NO DEBE medir los ficheros que `git` marca como binarios ni los de `limits.exclude`.
- **AC-04**: SI la rama crea un fichero por encima del límite o lo hace pasar de ≤ límite a > límite, ENTONCES `mth trace` DEBE reportarlo como error con la medida antes y después.
- **AC-05**: SI la rama hace crecer un fichero que ya superaba el límite, ENTONCES `mth trace` DEBE reportarlo como error, y un renombrado que git detecta DEBE compararse con su origen.
- **AC-06**: SI la rama toca un fichero por encima del límite sin hacerlo crecer, o no lo toca, ENTONCES `mth trace` DEBE avisar sin error.
- **AC-07**: MIENTRAS la rama actual no tenga rama padre, `mth trace` DEBE tratar los ficheros largos como avisos.
- **AC-08**: SI hay ficheros largos que comparar y la rama padre no se puede leer, ENTONCES `mth trace` DEBE fallar nombrando la causa.
- **AC-09**: SI un fichero con excepción supera su `max_lines`, ENTONCES `mth trace` DEBE reportarlo como error; dentro del techo NO DEBE reportar nada.
- **AC-10**: SI ningún fichero de una excepción supera el límite, ENTONCES `mth trace` DEBE reportarla como caducada.
- **AC-11**: CUANDO hay avisos de tamaño, `mth trace` DEBE resumirlos sin cambiar el código de salida, y `--limits` DEBE listarlos.
- **AC-12**: PRINCIPLES §5, `revisor-diseno` y sus evals DEBEN recoger la regla y el criterio del `reason`.
- **AC-13**: Los ficheros del propio repo DEBEN cumplir el límite o declarar su excepción.

## Notas

- Numeración: el «ADR-0014» del encargo (+1 de la sesión) ya existía; este es ADR-0016.

# SPEC-0022 · Gate de secretos en el historial

- Estado: aprobada
- Fecha: 2026-11-26
- Formato: compacto
- ADRs: [ADR-0020](../adr/security/ADR-0020-gate-de-secretos-en-el-historial.md)
- Sustituye a: —

## Contexto

- Un secreto en el historial compartido está comprometido y no se puede deshacer reescribiendo historia.
- [ADR-0020](../adr/security/ADR-0020-gate-de-secretos-en-el-historial.md) fija un gate en `mth integrate` con `gitleaks`, una línea base explícita y una decisión nunca silenciosa.

## Objetivo

1. Con `secrets.mode = "block"`, una rama con un secreto nuevo no se integra ni se sube.
2. Los secretos que ya había se aceptan de forma explícita y no bloquean.
3. Un repo adoptado se entera de que falta decidir, sin cambiarle nada solo.

## Fuera de alcance

- Hook de precommit y plantilla de workflow de CI.
- Otros escáneres distintos de `gitleaks`.
- Reescribir o limpiar historia.
- Escaneo de dependencias y análisis estático (otra spec).

## Comportamiento

### Configuración

| Clave | Por defecto | Significa |
|---|---|---|
| `secrets.mode` | `""` | `""` sin decidir · `"off"` desactivado · `"block"` el gate bloquea |
| `secrets.baseline` | `.gitleaks-baseline.json` | Informe redactado de hallazgos aceptados, relativo a la raíz |

### `mth secrets`

| Forma | Escanea |
|---|---|
| `mth secrets` | Los commits de la rama sobre su destino (`<remoto>/<destino>..HEAD`) |
| `mth secrets --history` | Todo el historial alcanzable |
| `mth secrets --history --accept` | Todo el historial y escribe `secrets.baseline` con los hallazgos |

- Ejecuta `gitleaks git` con `--redact`, `--no-banner` y `--exit-code 2`: 0 limpio, 2 hallazgos, otro valor es fallo de la herramienta.
- Pasa `--baseline-path` solo si el fichero de línea base existe.
- El informe temporal vive en un directorio temporal que se borra siempre.
- Cada hallazgo se imprime como `regla · fichero:línea · commit` (hash de 8 caracteres); nunca el valor.
- `mth secrets` funciona con cualquier `secrets.mode`; el modo solo decide el gate de `mth integrate`.

### Gate de `mth integrate`

- Corre tras la trazabilidad y antes de la revisión y los tests, y antes de subir.
- `block`: ejecuta el escaneo de la rama. `off`: no hace nada. `""`: avisa de que falta decidir y sigue.

### Diagnóstico

- `mth doctor`: `block` con `gitleaks` ausente → ✗; `""` o `off` → ⚠ con el remedio.
- `mth update --plan`: brecha `secretos` de clase `decision` mientras `secrets.mode = ""`.

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | `secrets.mode` desconocido o `secrets.baseline` vacío | Error de configuración; ningún comando corre | AC-01 |
| FM-02 | `gitleaks` no instalado y se necesita | Error con el remedio de instalación; no se da por limpio | AC-08 |
| FM-03 | `gitleaks` falla (código distinto de 0 y 2) o el informe no se puede leer | Error que nombra la causa; bloquea | AC-09 |
| FM-04 | Hallazgo real | Se imprime sin el valor y bloquea | AC-03 |
| FM-05 | Línea base inexistente | Se escanea sin ella | AC-05 |
| FM-06 | El informe temporal queda en disco | Se borra siempre, también ante error | AC-10 |
| FM-07 | Aceptar un hallazgo sin rotarlo | `--accept` avisa de que hay que rotar | AC-06 |

## Criterios de aceptación

- **AC-01**: SI `secrets.mode` no es `""`, `"off"` ni `"block"`, o `secrets.baseline` está vacío, ENTONCES la carga de la configuración DEBE fallar nombrando la clave.
- **AC-02**: CUANDO se ejecuta `mth secrets`, `mth` DEBE escanear los commits de la rama sobre su destino y `mth secrets --history` todo el historial.
- **AC-03**: SI el escaneo encuentra secretos, ENTONCES `mth secrets` DEBE terminar con error y listar regla, fichero, línea y commit corto sin imprimir el valor.
- **AC-04**: SI no hay hallazgos, ENTONCES `mth secrets` DEBE terminar con éxito.
- **AC-05**: MIENTRAS exista el fichero de línea base, `mth secrets` DEBE pasarlo a `gitleaks`, y los hallazgos que contiene NO DEBEN bloquear; sin fichero DEBE escanear sin él.
- **AC-06**: CUANDO se ejecuta `mth secrets --history --accept`, `mth` DEBE escribir la línea base con los hallazgos y avisar de que los secretos deben rotarse.
- **AC-07**: CUANDO `secrets.mode = "block"`, `mth integrate` DEBE escanear la rama antes de subirla y, con un hallazgo, DEBE fallar sin subir; con `"off"` NO DEBE escanear; con `""` DEBE avisar de que falta decidir.
- **AC-08**: SI `gitleaks` no está instalado, ENTONCES `mth secrets` y el gate DEBEN fallar con el remedio y NO DEBEN darlo por limpio.
- **AC-09**: SI `gitleaks` termina con un código distinto de 0 y 2 o su informe no es legible, ENTONCES `mth` DEBE fallar nombrando la causa.
- **AC-10**: `mth secrets` DEBE borrar el informe temporal también cuando el escaneo falla.
- **AC-11**: `mth doctor` DEBE marcar ✗ con `block` y `gitleaks` ausente, y ⚠ con `""` o `off`.
- **AC-12**: MIENTRAS `secrets.mode = ""`, `mth update --plan` DEBE listar la brecha `secretos` de clase `decision`; con `"off"` o `"block"` NO DEBE listarla.
- **AC-13**: El README, `mth-update` y `mth-init` DEBEN documentar `[secrets]`, `mth secrets` y la brecha, y `revisor-seguridad` DEBE vigilar `secrets.baseline` y `secrets.mode`.

## Notas

- Tests con un `gitleaks` falso en `PATH` (no se exige la herramienta real para correr la suite).
- Este repo queda sin decidir (`""`) hasta que la persona elija; `mth update --plan` lo mostrará.

# SPEC-0027 · Auditor estático y packs de línea base

- Estado: implementada
- Fecha: 2026-11-27
- Formato: compacto
- ADRs: [ADR-0024](../adr/security/ADR-0024-packs-de-linea-base-en-toml-y-verificacion-del-informe.md)
- Sustituye a: —
- Seguridad: entrada externa

## Contexto

- Fase 4a de la hoja de ruta de seguridad: un auditor de hardening que lee el repo y corre herramientas offline contra una línea base verificable.
- El informe del modelo no es fiable por sí solo: `mth` valida su forma contra datos.

## Objetivo

1. `mth audit packs` lista y valida los packs y avisa de los caducados.
2. `mth audit verify` valida un informe contra su pack.
3. El agente `auditor-estatico` audita un dominio con las herramientas offline y escribe el informe.
4. Packs de la primera iteración: `comun`, `docker` y `kubernetes`.

## Fuera de alcance

- Red y destinos remotos (auditor de ejecución). Packs de Terraform, TLS, SSH, bases de datos, kernel y VPN.
- Instalar `hadolint`, `trivy` o `checkov`. Certificar cumplimiento de una norma.

## Comportamiento

| Elemento | Regla |
|---|---|
| Packs | `plugins/methodology/audit/packs/<id>.toml` según ADR-0024 |
| `mth audit packs` | Una línea por pack: id, versión, controles, revisado, `vigente`/`caducado`, hash corto. Falla si un pack es inválido |
| `mth audit verify <informe>` | Reglas de ADR-0024 decisión 4; una línea por problema; código ≠ 0 si hay alguno |
| `mth doctor` | Aviso (no bloqueante) por pack caducado |
| Agente `auditor-estatico` | Catálogo, perfil `opcional`; guard solo de lectura más herramientas offline y `mth audit`; escribe en `.work/security-report/` |
| Skill `mth-audit` | Un agente por dominio, en paralelo; `mth audit verify` antes de entregar |

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | Pack con TOML inválido, campo ausente o ID repetido | `mth audit packs` falla y nombra el pack | AC-02 |
| FM-02 | Informe cita un control que no existe | `verify` lo rechaza | AC-05 |
| FM-03 | Falta resultado de un control `minimo` | `verify` lo rechaza | AC-06 |
| FM-04 | Pack alterado tras el informe | El hash no coincide y `verify` lo rechaza | AC-08 |
| FM-05 | Herramienta ausente | El control queda `no evaluable` | AC-12 |

## Criterios de aceptación

- **AC-01**: CUANDO se ejecuta `mth audit packs`, el sistema DEBE listar cada pack con id, versión, número de controles, fecha de revisión, estado y hash.
- **AC-02**: SI un pack no es TOML válido, le falta un campo obligatorio o repite un ID de control, ENTONCES `mth audit packs` DEBE fallar nombrando el pack.
- **AC-03**: CUANDO `reviewed` más `review_months` queda en el pasado, `mth audit packs` DEBE marcar el pack como caducado y `mth doctor` DEBE avisar sin bloquear.
- **AC-04**: CUANDO un informe cumple el formato, `mth audit verify` DEBE aceptarlo con código 0.
- **AC-05** [SEG]: SI un informe cita un control que el pack no define, ENTONCES `mth audit verify` DEBE rechazarlo.
- **AC-06**: SI un control `minimo` no tiene resultado en el informe, ENTONCES `mth audit verify` DEBE rechazarlo.
- **AC-07**: SI un resultado no es `cumple`, `no cumple` o `no evaluable`, o un `cumple`/`no cumple` no lleva evidencia, ENTONCES `mth audit verify` DEBE rechazarlo.
- **AC-08** [SEG]: SI la línea de base del informe no coincide con el pack y su hash, ENTONCES `mth audit verify` DEBE rechazarlo.
- **AC-09**: SI el informe contiene «certificado» o «certifica», ENTONCES `mth audit verify` DEBE rechazarlo.
- **AC-10**: Los packs `comun`, `docker` y `kubernetes` DEBEN ser válidos, con fuente, fecha de revisión y controles con título propio.
- **AC-11** [SEG]: El agente `auditor-estatico` DEBE ser de solo lectura: su guard permite git de lectura, `mth audit` y herramientas offline, y deniega red, escritura fuera de `.work/security-report/` y el resto de `mth`.
- **AC-12**: SI la herramienta de un control no está disponible, ENTONCES el agente DEBE marcarlo `no evaluable`, según su texto.
- **AC-13**: La skill `mth-audit`, el agente y el README DEBEN documentar el flujo y que nunca certifican.

## Notas

- Los IDs de reglas de `docker` se verificaron en el README de hadolint y los de `kubernetes` en Pod Security Standards (2026-11-27).

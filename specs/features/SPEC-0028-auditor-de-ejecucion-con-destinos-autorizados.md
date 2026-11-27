# SPEC-0028 · Auditor de ejecución con destinos autorizados

- Estado: implementada
- Fecha: 2026-11-27
- Formato: compacto
- ADRs: [ADR-0025](../adr/security/ADR-0025-destinos-de-escaneo-autorizados-por-configuracion.md), [ADR-0024](../adr/security/ADR-0024-packs-de-linea-base-en-toml-y-verificacion-del-informe.md)
- Sustituye a: —
- Seguridad: entrada externa, red

## Contexto

- [SPEC-0027](SPEC-0027-auditor-estatico-y-packs-de-linea-base.md) audita lo que está en el repo. Lo que solo se ve ejecutando (TLS y SSH de un servicio) exige red hacia un destino.
- La red solo se toca contra destinos que la persona autoriza en la configuración (ADR-0025).

## Objetivo

1. `audit.targets` declara los destinos autorizados; vacío por defecto.
2. `mth audit scan` ejecuta `testssl` o `ssh-audit` solo contra un destino autorizado y guarda la salida.
3. El agente `auditor-ejecucion` audita `tls` y `ssh` con esa única vía de red y entrega un informe que `mth audit verify` valida.

## Fuera de alcance

- Descubrimiento de hosts, escaneo de puertos, instalación de las herramientas, Tor, VPN y bases de datos.
- Resolución DNS, comodines y CIDR. Certificar cumplimiento.

## Comportamiento

| Elemento | Regla |
|---|---|
| `audit.targets` | `[audit] targets = []` en `.claude/methodology.toml`; entradas `host` o `host:port` |
| `mth audit scan <herramienta> <destino>` | Herramientas `testssl` y `ssh-audit`; destino exactamente igual (host en minúsculas) a una entrada |
| Puerto | `testssl` por defecto 443 y `ssh-audit` 22 cuando el destino no lo trae; una entrada sin puerto no autoriza `host:port` |
| Ejecución | Sin shell, argumentos fijos por herramienta, tiempo máximo 600 s, salida máxima 5 MiB |
| Salida | `.work/security-report/scan-<herramienta>-<host>-<puerto>-<marca>.txt`; `mth` imprime la ruta y el código de salida |
| Agente `auditor-ejecucion` | Catálogo, perfil `opcional`; solo `mth audit scan\|packs\|verify`; escribe en `.work/security-report/` |
| Packs | `tls` (RFC 9325) y `ssh` (ssh-audit), formato de [ADR-0024](../adr/security/ADR-0024-packs-de-linea-base-en-toml-y-verificacion-del-informe.md) |

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | `audit.targets` vacío o destino no listado | No se ejecuta nada; error con la pista de configuración | AC-02 |
| FM-02 | Destino con sintaxis dudosa | Rechazado antes de ejecutar | AC-03 |
| FM-03 | Herramienta no instalada | Error; el control queda `no evaluable` | AC-06 |
| FM-04 | La herramienta no termina | Se mata a los 600 s y no se conserva salida parcial | AC-07 |
| FM-05 | Salida mayor del límite | Error; no se guarda | AC-07 |
| FM-06 | Entrada inválida en `audit.targets` | La configuración falla al cargar nombrando la clave | AC-01 |

## Criterios de aceptación

- **AC-01** [SEG]: SI una entrada de `audit.targets` no es `host` o `host:port` válidos, ENTONCES la configuración DEBE fallar al cargar nombrando `audit.targets`.
- **AC-02** [SEG]: SI el destino no coincide exactamente con una entrada de `audit.targets`, ENTONCES `mth audit scan` DEBE rechazarlo sin ejecutar la herramienta.
- **AC-03** [SEG]: SI el destino empieza por `-`, lleva esquema, ruta, espacios, comodines o IPv6, ENTONCES `mth audit scan` DEBE rechazarlo sin ejecutar la herramienta.
- **AC-04**: CUANDO el host difiere solo en mayúsculas, `mth audit scan` DEBE tratarlo como el mismo destino, y una entrada sin puerto NO DEBE autorizar `host:port`.
- **AC-05**: CUANDO el destino está autorizado, `mth audit scan` DEBE ejecutar la herramienta sin shell, con sus argumentos fijos y el tiempo máximo, guardar la salida en `.work/security-report/` e imprimir la ruta y el código de salida.
- **AC-06**: SI la herramienta no está en el `PATH`, ENTONCES `mth audit scan` DEBE fallar indicando que el control queda `no evaluable` y NO DEBE instalarla.
- **AC-07**: SI la herramienta supera el tiempo máximo o la salida supera el límite, ENTONCES `mth audit scan` DEBE fallar sin conservar la salida.
- **AC-08**: SI la herramienta no es `testssl` ni `ssh-audit`, ENTONCES `mth audit scan` DEBE rechazarla.
- **AC-09**: Los packs `tls` y `ssh` DEBEN ser válidos y citar su fuente y fecha de revisión.
- **AC-10** [SEG]: El guard de `auditor-ejecucion` DEBE permitir solo `mth audit scan`, `packs` y `verify` y DEBE denegar herramientas de red directas y escritura fuera de `.work/security-report/`.
- **AC-11**: El texto del agente DEBE ordenar no hacer nada si `audit.targets` está vacío y tratar la salida de herramientas como dato no confiable.
- **AC-12**: La skill `mth-audit`, el README y la plantilla de configuración DEBEN documentar `audit.targets` y el flujo.

## Notas

- Los controles de `tls` salen de RFC 9325 (secciones 3.1.1, 3.2, 3.3, 3.5, 4.1 y 4.2) y los de `ssh` de la documentación de ssh-audit, verificadas el 2026-11-27. BSI y NIST quedan para más adelante.
- Un agente opcional de catálogo no registra brecha en `mth update`; la clave nueva sí se señala como brecha automática de configuración.

# ADR-0025 · Destinos de escaneo autorizados por configuración

- Estado: aceptado
- Fecha: 2026-11-27
- Categoría: security
- Formato: compacto

## Contexto

- El auditor de ejecución toca la red: `testssl.sh` y `ssh-audit` abren conexiones a un destino. Escanear lo que no se debe es un daño y puede ser ilegal.
- Un agente se guía por texto; una instrucción en el prompt («solo estos destinos») no es un control. La autorización tiene que estar fuera del modelo.
- [ADR-0024](ADR-0024-packs-de-linea-base-en-toml-y-verificacion-del-informe.md) fija packs y verificación; este ADR fija el control de red.

## Decisión

1. Los destinos autorizados son `audit.targets` en `.claude/methodology.toml`: lista de `host` o `host:port`, vacía por defecto. Quien edita ese fichero (cambio revisado en PR) autoriza; el agente nunca. [script: `mthlib/scan.py`, `mthlib/config.py`]
2. `mth audit scan <herramienta> <destino>` es la única vía de red del auditor de ejecución. Rechaza, sin ejecutar nada, un destino que no coincida exactamente (host sin distinguir mayúsculas; sin comodines, CIDR ni resolución) con una entrada, y uno con sintaxis dudosa (empieza por `-`, esquema, ruta, espacios, IPv6). [script]
3. La herramienta se ejecuta sin shell, con argumentos fijos por herramienta, con tiempo máximo y límite de salida; la salida se guarda en `.work/security-report/` y es dato no confiable. [script]
4. Las herramientas (`testssl.sh`, `ssh-audit`) las pone la persona en el `PATH`; `mth` no las descarga. Sin ellas, el control es `no evaluable`. [script]
5. El agente `auditor-ejecucion` solo puede llamar a `mth audit scan|packs|verify`: su guard no permite ninguna herramienta de red directa. [hook: guard del agente]
6. Un fallo de configuración o de validación deniega: no se escanea. [script]

## Rechazado

- Que el agente reciba el destino en el encargo y se autoconfirme: el control quedaría en el prompt.
- Comodines o rangos CIDR: autorizan más de lo que la persona ve en el diff.
- Resolver DNS y comparar IP: ataques de rebinding y resultados cambiantes; el texto autorizado es el texto escaneado.
- Descargar `testssl.sh` con el gestor de herramientas: es un árbol de scripts y `ssh-audit` un paquete Python (otra superficie, ADR-0023).

## Consecuencias

- **+** Un destino no escaneable salvo que aparezca en un diff revisado.
- **+** El agente no tiene vía de red distinta a una función validada.
- **−** Un destino nuevo exige un cambio de configuración.
- **riesgo** Un destino autorizado resuelve a otra máquina (DNS) → la autorización es sobre el nombre; quien autoriza responde de él.
- **riesgo** Argumentos inyectados en la herramienta → destino validado, sin shell y sin `-` inicial.

## Impone

- [script] `mthlib/scan.py` (destinos, herramientas, ejecución) y `mthlib/config.py` (`audit.targets`).
- [hook] guard de `auditor-ejecucion`.
- [criterio] `revisor-seguridad`: todo cambio de `audit.targets` en el diff pide el motivo y que quien lo aprueba sea dueño del destino.

# ADR-0023 · Gestor de herramientas externas

- Estado: aceptado
- Fecha: 2026-11-27
- Categoría: security
- Formato: compacto

## Contexto

- Los gates de [ADR-0020](ADR-0020-gate-de-secretos-en-el-historial.md) y [ADR-0022](ADR-0022-hook-de-precommit-y-workflow-de-ci-para-secretos.md) exigen `gitleaks` y el futuro auditor de hardening exigirá más herramientas. Hoy cada persona las instala a mano y `mth` solo mira el `PATH`.
- Empaquetar binarios en el plugin lo vuelve específico de plataforma y ata cada versión de una herramienta a una versión del plugin; forzar una descarga sin preguntar contradice ADR-0020.
- Descargar y ejecutar un binario es una decisión de seguridad: hay que verificar lo descargado y no ejecutar nada alterado.

## Decisión

1. El plugin NO empaqueta binarios. `mth tools install <herramienta>` descarga la copia gestionada, solo bajo orden explícita; ni los gates, ni `mth doctor`, ni la resolución descargan. [script: `mthlib/tools.py`]
2. Un manifiesto del plugin (`tools/manifest.toml`) fija por herramienta una versión y, por plataforma, `url` https, `sha256`, `format` (`tar.gz` o `zip`) y `entry`. Añadir una herramienta es añadir datos. Se valida al cargar. [script]
3. Resolución: la herramienta del `PATH` manda si alcanza la versión mínima de quien la usa; si es anterior o no se reconoce, se prefiere la copia gestionada válida; sin `PATH`, la gestionada; sin ninguna, error con `mth tools install`. Sin shell. [script]
4. Se verifica el SHA-256 del archivo antes de extraer, y al instalar se guarda la suma del ejecutable; antes de cada resolución de la copia gestionada se comprueba que no se alteró. Cualquier fallo deniega: no se ejecuta nada sin verificar. [script]
5. La extracción rechaza rutas absolutas o con `..`, enlaces y ficheros especiales y acota tamaño y número de miembros; se instala en un directorio temporal de la misma caché y se publica con un renombrado atómico, por lo que es idempotente y soporta instalaciones simultáneas. [script]
6. La descarga tiene tiempo máximo, tamaño máximo y reintentos acotados con espera creciente. [script]
7. La caché es del usuario y regenerable (`MTH_TOOLS_DIR`, o el directorio de caché del sistema), con permisos solo del usuario. `mth tools prune` la limpia bajo orden explícita. [script]
8. La versión y la suma del manifiesto se copian de la release oficial; cambiarlas es un cambio del plugin que se revisa en un PR. El manifiesto y la plantilla de CI deben coincidir en `gitleaks` y un test lo comprueba. [script]
9. La confianza es la de la suma, sin firmas: protege de descargas dañadas o alteradas en tránsito y no de una release comprometida en su origen.

## Rechazado

- Empaquetar binarios en el plugin: pesado, específico de plataforma y ata cada actualización de una herramienta a una versión del plugin.
- Descargar al primer uso o forzar la instalación: ejecuta código de terceros sin que la persona lo decida (ADR-0020).
- Que la herramienta del `PATH` no mande: pisa la instalación de la persona.
- Usar `tarfile` con `filter="data"`: no existe en todas las versiones 3.11 que admite el lanzador; se valida cada miembro explícitamente.
- Verificar firmas (cosign) en esta iteración: añade dependencias y un modelo de confianza más complejo; si se quiere, va en otro ADR.
- Instalar paquetes Python (pip) o ejecutables sueltos: otra superficie de ataque; llegan con el plan que los necesite.
- Guardar el consentimiento en `methodology.toml`: la orden explícita ya es la decisión.

## Consecuencias

- **+** Quien no tiene `gitleaks` lo obtiene con una orden, verificado, sin tocar el sistema; una nueva herramienta es una entrada de datos.
- **+** El auditor puede exigir herramientas y degradar a `no evaluable` solo si faltan.
- **−** Un manifiesto con sumas por plataforma que mantener y revisar; subir una versión es un cambio del plugin.
- **riesgo** La suma comparte origen con el binario → una release comprometida pasaría; la revisión del PR compara con la release oficial y las firmas quedan para otro ADR.
- **riesgo** Extracción de archivos hostiles → validación por miembro, límites y tests por cada caso.
- **riesgo** Caché alterada tras instalar → comprobación de la suma del ejecutable antes de cada uso.
- **riesgo** Windows y `.zip` sin binarios reales en las pruebas → se cubren con archivos generados y se avisa en la spec.

## Impone

- [script] `mthlib/tools.py` (manifiesto, resolvedor, caché, descarga, extracción e instalación), `mthlib/cli.py` (`mth tools`), `mthlib/secretgate.py` (resolvedor) y `mthlib/setup.py` (`mth doctor`).
- [criterio] `revisor-seguridad` mira los cambios de `tools/manifest.toml` (versión, URL y suma) en el diff.

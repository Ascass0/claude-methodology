# ADR-0024 · Packs de línea base en TOML y verificación del informe

- Estado: aceptado
- Fecha: 2026-11-27
- Categoría: security
- Formato: compacto

## Contexto

- La fase 4 de la hoja de ruta de seguridad añade auditores de hardening. Un modelo que audita contra su memoria inventa controles y emite veredictos que parecen certificaciones.
- La hoja de ruta de seguridad pedía packs en YAML; el plugin es solo stdlib ([ADR-0023](ADR-0023-gestor-de-herramientas-externas.md)) y Python no lee YAML.

## Decisión

1. La línea base de cada dominio es un pack: un fichero TOML versionado en `plugins/methodology/audit/packs/`, leído con `tomllib`. Sustituye al YAML de la hoja de ruta con los mismos campos. [script: `mthlib/audit.py`]
2. Un pack declara `id`, `title`, `version`, `reviewed` (fecha), `review_months`, `source` (nombre, versión de la norma y URL oficial) y controles con `id`, `title` propio, `level` (`minimo`|`recomendado`), `url`, `tool` y `rule` (vacíos = revisión manual). NO DEBE contener texto con licencia de la norma. [script]
3. Los controles son datos verificados en su fuente al crear o revisar el pack, nunca de la memoria del modelo; un control sin fuente verificable no entra. [criterio]
4. El informe de un auditor cita `Línea base: <pack>@<versión> sha256=<hash del fichero>` y una línea `- <ID> | cumple|no cumple|no evaluable | evidencia` por control. `mth audit verify` rechaza IDs inexistentes, controles `minimo` sin resultado, estados fuera del conjunto, `cumple`/`no cumple` sin evidencia, un hash que no coincide y las palabras «certificado» o «certifica». [script]
5. Un pack con `reviewed` + `review_months` vencido se marca caducado en `mth audit packs` y `mth doctor` avisa; `mth doctor` avisa, y el agente declara un pack caducado en su informe. [script]
6. La web solo actualiza packs en una tarea de mantenimiento con PR y revisión humana, desde fuentes oficiales; una auditoría nunca cambia su resultado por lo que lea. [criterio]

## Rechazado

- YAML: obliga a una dependencia o a un parser propio.
- Controles generados por el modelo en cada auditoría: no reproducibles ni verificables.
- Copiar el texto de CIS, NIST u otras normas: licencias; se guardan ID, título propio y enlace.
- Un veredicto global «cumple»: se confunde con certificación.

## Consecuencias

- **+** Un script comprueba que el informe cita solo controles reales y completos.
- **+** El informe es reproducible: versión y hash de la línea base.
- **−** Cada pack es trabajo de mantenimiento con revisión de su fuente.
- **riesgo** Pack desactualizado → caducidad con aviso.
- **riesgo** Evidencia inventada → `verify` solo comprueba forma; `revisor-seguridad` y la persona leen la evidencia.

## Impone

- [script] `mthlib/audit.py` (validación de packs y de informes), `mth audit packs|verify`, `mthlib/setup.py` (aviso de caducidad).
- [criterio] Todo cambio en `audit/packs/` cita la fuente verificada en el PR.

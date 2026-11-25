# SPEC-0006 · Hooks commit-msg encadenados

- Estado: implementada
- Fecha: 2026-11-18
- Formato: compacto
- ADRs: ADR-0003
- Sustituye a: —


## Contexto

- `mth` nunca sobrescribe un hook `commit-msg` ajeno: lo deja, informa de que es ajeno y la validación de la metodología no se activa. Es seguro, pero deja dos opciones sin resolver.
- Sustituirlo, cuando el repo solo validaba el formato y la metodología lo cubre.
- Encadenarlo, cuando hace algo más (p. ej. añadir un número de ticket) y debe seguir funcionando.
- La adopción guiada ([SPEC-0004](SPEC-0004-adopcion-guiada.md)) pregunta cuál quiere el repo.

## Objetivo

El repo declara qué hacer con un hook `commit-msg` ajeno: conservarlo (como hasta ahora), sustituirlo guardando una copia o encadenarlo con el de la metodología.

## Fuera de alcance

- Los gestores de hooks que regeneran sus ficheros (husky, lefthook, pre-commit): su directorio de hooks está versionado y `mth` no lo toca.
- Otros hooks además de `commit-msg`.

## Comportamiento

Clave nueva `hooks.commit_msg`, con uno de estos valores:

- **`own`** (por defecto): el comportamiento actual. Instala el hook si no hay ninguno o si el que hay es de la metodología, y deja intacto uno ajeno (estado `foreign`).
- **`replace`**: si el hook es ajeno, lo renombra a `commit-msg.pre-mth` e instala el de la metodología (estado `replaced`). Si `commit-msg.pre-mth` ya existe, falla sin tocar nada.
- **`chain`**: si el hook es ajeno, lo renombra a `commit-msg.local` e instala el de la metodología, que ejecuta primero `commit-msg.local "$1"` y, si termina bien, la validación de `mth` (estado `chained`). Si cualquiera de los dos rechaza el mensaje, el commit se rechaza. Volver a instalar es idempotente: no mueve nada que ya esté encadenado.

El hook se instala, como hasta ahora, con `mth init`, `mth doctor` y el hook de sesión. `mth doctor` muestra el estado.

Si el directorio de hooks de git está dentro del árbol de trabajo (`core.hooksPath` apuntando a una carpeta versionada, como hace un gestor de hooks), `replace` y `chain` fallan con un error que explica cómo añadir `mth check-msg "$1"` al gestor, y no modifican nada.

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | Valor desconocido en `hooks.commit_msg` | Fail-fast al cargar la configuración | AC-06 |
| FM-02 | `replace` con `commit-msg.pre-mth` ya existente | Error al instalar; no se toca ningún fichero | AC-02 |
| FM-03 | Directorio de hooks versionado con `replace` o `chain` | Error con la instrucción para el gestor de hooks; no se toca nada | AC-05 |
| FM-04 | `commit-msg.local` desaparece o deja de ser ejecutable tras encadenar | El hook rechaza el commit con un mensaje que lo explica (no se valida a medias) | AC-07 |

## Criterios de aceptación

- **AC-01**: MIENTRAS `hooks.commit_msg` sea `own` o no exista, un hook ajeno DEBE quedar intacto con estado `foreign`.
- **AC-02**: CUANDO `hooks.commit_msg = "replace"` y el hook es ajeno, `mth` DEBE renombrarlo a `commit-msg.pre-mth` e instalar el de la metodología; SI la copia ya existe, ENTONCES DEBE fallar sin modificar nada.
- **AC-03**: CUANDO `hooks.commit_msg = "chain"` y el hook es ajeno, `mth` DEBE renombrarlo a `commit-msg.local`; el commit DEBE rechazarse si lo rechaza el hook encadenado o la validación de `mth`, y aceptarse si los dos lo aceptan.
- **AC-04**: CUANDO se instala dos veces con `chain`, `mth` DEBE dejar el mismo resultado que con una.
- **AC-05**: SI el directorio de hooks está dentro del árbol de trabajo, ENTONCES `replace` y `chain` DEBEN fallar sin modificar nada.
- **AC-06**: SI `hooks.commit_msg` no es `own`, `replace` o `chain`, ENTONCES la carga de la configuración DEBE rechazarlo.
- **AC-07**: SI con `chain` `commit-msg.local` no existe o no es ejecutable, ENTONCES el hook DEBE rechazar el commit.

## Notas

—

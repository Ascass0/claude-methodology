# SPEC-0006 · Hooks commit-msg encadenados

- Estado: aprobada
- Fecha: 2026-11-18
- ADRs: ADR-0003
- Sustituye a: —

<!-- Estados: borrador → aprobada → implementada → sustituida.
     "implementada" exige que cada AC tenga un test con `verifies: SPEC-0006/AC-NN`. -->

## Contexto

`mth` nunca sobrescribe un hook `commit-msg` ajeno: lo deja en su sitio, informa de que es ajeno y la validación de mensajes de la metodología no se activa. Es el comportamiento seguro, pero deja dos opciones sin resolver. Una es sustituir el hook ajeno, cuando el repo solo validaba el formato y la metodología lo cubre. La otra es encadenarlo, cuando el hook hace algo más (por ejemplo, añadir un número de ticket) y debe seguir funcionando. La adopción guiada ([SPEC-0004](SPEC-0004-adopcion-guiada.md)) pregunta cuál quiere el repo.

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

| Fallo | Detección | Respuesta (estado seguro) |
|---|---|---|
| Valor desconocido en `hooks.commit_msg` | Carga de la configuración | Fail-fast |
| `replace` con `commit-msg.pre-mth` ya existente | Instalación del hook | Error; no se toca ningún fichero |
| Directorio de hooks versionado con `replace` o `chain` | Instalación del hook | Error con la instrucción para el gestor de hooks; no se toca nada |
| `commit-msg.local` desaparece o deja de ser ejecutable después de encadenarlo | Hook `commit-msg` | Se rechaza el commit con un mensaje que lo explica (no se valida a medias) |

## Criterios de aceptación

- **AC-01**: Con `hooks.commit_msg = "own"` o sin la clave, un hook ajeno queda intacto y su estado es `foreign`.
- **AC-02**: Con `replace`, un hook ajeno se renombra a `commit-msg.pre-mth` y se instala el de la metodología; si la copia ya existe, la instalación falla sin modificar nada.
- **AC-03**: Con `chain`, un hook ajeno se renombra a `commit-msg.local`, y el commit se rechaza si lo rechaza el hook encadenado o la validación de `mth`, y se acepta si los dos lo aceptan.
- **AC-04**: Instalar dos veces con `chain` deja el mismo resultado que instalar una vez.
- **AC-05**: Con un directorio de hooks dentro del árbol de trabajo, `replace` y `chain` fallan sin modificar nada.
- **AC-06**: La carga de la configuración rechaza un valor de `hooks.commit_msg` distinto de `own`, `replace` o `chain`.
- **AC-07**: Con `chain`, si `commit-msg.local` no existe o no es ejecutable, el hook rechaza el commit.

## Notas

—

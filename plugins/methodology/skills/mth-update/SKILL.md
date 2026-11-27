---
name: mth-update
description: Pone un repo ya adoptado al día con la versión instalada del plugin (claves de configuración, agentes del catálogo, bloque de CLAUDE.md, hook, formato de specs y ADR). Solo la lanza la persona.
model: opus
disable-model-invocation: true
---

# Actualizar el repo al plugin nuevo

`mth` es el comando del contexto de sesión (`$MTH`). El repo ya adoptó la metodología y el plugin ha cambiado: se trae lo nuevo sin tocar ninguna decisión ya tomada. Cambiar una decisión es `mth-reconfigure`; un repo sin `.claude/methodology.toml` es `mth-init`.

## 1. Diagnóstico

1. Árbol limpio y sin `chore/update-methodology` abierta (si estás en ella, se reanuda). Si no, díselo a la persona y para.
2. `mth update --plan` (solo lee). Presenta las brechas por clase:

| Clase | Qué hace `mth` |
|---|---|
| `automatica` | La aplica `mth update` sin criterio humano |
| `decision` | La conduces tú con aprobación (paso 3) |
| `informativa` | Solo se informa: no se aplica |

Sin brechas, di «al día» y termina.

## 2. Lo automático

`mth update`: crea `chore/update-methodology`, aplica solo las `automatica` en un único commit con su ADR de actualización y sube la rama. No cambia ningún valor ya decidido. Si falla a medias, vuelve a ejecutarlo en esa rama: aplica lo que falta.

## 3. Decisiones

Pregunta con `AskUserQuestion`, en una sola ronda y solo lo que `mth update --plan` marca como `decision`:

| Brecha | Opciones |
|---|---|
| `agentes-perfil` | Instalar los agentes que acepte (`mth agents add <agentes>`) o ninguno. Rellena su sección local con lo que sabes del repo |
| `agentes-editados` | `mth agents sync <agente> --force` (pierde la edición de la parte generada) o conservar |
| `secretos` | Pregunta si activar el gate de secretos (`secrets.mode = "block"`, requiere `gitleaks`) o desactivarlo (`"off"`); si hay historial previo, `mth secrets --history` lo diagnostica y `--accept` acepta lo ya existente (rota esos secretos). Anota la decisión en el ADR de actualización |
| `secretos-hook` | Pregunta si activar el hook `pre-commit` (`secrets.hook = "on"`, requiere `gitleaks` ≥ 8.19.0) o no (`"off"`). Con un hook `pre-commit` ajeno, pregunta también `hooks.pre_commit` (`own`, `replace`, `chain`). Anota la decisión en el ADR de actualización |
| `secretos-ci` | Solo con GitHub y `ci.required = true`: pregunta si activar el workflow de secretos (`secrets.ci = "on"`) o no (`"off"`). Recuerda que la protección de rama debe exigir su comprobación. Anota la decisión en el ADR de actualización |
| `formato` | Convertir los specs y ADR al formato compacto, o dejarlos como están |

- **`formato` con conversión:** presenta antes un plan por documento (qué se conserva y qué se reescribe) y pide aprobación. Ajusta solo lo que señale; tras tres rondas sin acuerdo, resume lo pendiente y no conviertas. Conserva los IDs de los criterios y los enlaces entre documentos; comprueba que no cambian respecto a `development`.
- Lo decidido se hace en la misma rama, en commits `chore(methodology)` o `docs`, y se anota en el ADR de actualización (la sección `Decisión` lista lo pendiente: actualízala).

## 4. Cierre

1. `mth doctor` sin ✗ y `mth trace` sin errores.
2. Integra con la skill `mth-integrate` (`--title "chore(methodology): update claude-methodology"`).
3. Mensaje final con tres listas: **aplicado** (lo automático), **decidido** (lo que respondió la persona) y **pendiente** (las `informativa`, p. ej. `mth smoke` o los criterios con un solo test, y lo que la persona dejó).

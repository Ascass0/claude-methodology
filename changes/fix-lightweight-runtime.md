---
bump: patch
refs: SPEC-0004, SPEC-0005, SPEC-0006, SPEC-0007, SPEC-0010, SPEC-0014, SPEC-0024, SPEC-0025
---
### Cambiado
- El guard de `Bash` tarda 36 ms por llamada en lugar de 128 ms: ya no carga la CLI ni la pila de red, y solo lee la configuración y git para comandos que mencionan git, gh, glab o mth.
- El hook de sesión pasa de 160 a 120 ms, y el hook `commit-msg` de 187 a 80 ms, al no cargar la CLI completa.
- El hook `pre-commit` de secretos ya no lanza gitleaks cuando el commit solo borra ficheros o no añade contenido (de 711 a 139 ms); sigue rechazando el commit si gitleaks falta, y con ficheros preparados los escanea como antes.
- `mth trace` lee cada documento una vez (de 638 a 267 lecturas) y baja de 366 a 299 ms, con la misma salida.

# Guía de Evidence Desk

Ejecute `make demo` y abra http://localhost:3101. Usuario Aurora: `analyst@aurora.example`; contraseña pública de demostración: `demo-evidence`. Meridian usa `analyst@meridian.example`. El indicador DEMO permanece visible.

Seleccione una pregunta sugerida, espere la respuesta y abra su cita para verificar documento, versión, sección y fragmento original. En Biblioteca puede cargar PDF con texto, TXT o Markdown, actualizar una versión, reintentar su procesamiento y eliminar un documento con confirmación. La extracción, persistencia, permisos y worker funcionan sin API keys. La búsqueda textual se identifica como tal. Una pregunta libre necesita LIVE; los ejemplos no pretenden interpretar texto arbitrario.

Las dos organizaciones son ficticias y sus manuales originales son sintéticos. No son políticas de una institución real. Las respuestas DEMO están ligadas al hash del manual original; si reemplaza ese contenido, el ejemplo se abstiene. Al eliminar el documento se eliminan índices y vínculos de citas correspondientes.

Pruebas: `make check types test build`; navegador: `cd apps/web && npm run test:e2e` con API/worker activos. Las capturas en `docs/screenshots` provienen del navegador real. Los contratos de los SDK de OpenAI y Gemini se verificaron con transportes simulados; no se enviaron llamadas pagadas. Las métricas de calidad de modelos y el despliegue Azure están pendientes.

Para LIVE siga [live.md](live.md): configure las claves solo en backend, cree un usuario LIVE mediante el comando de provisión, cargue documentos para indexar y ejecute el smoke test opcional. Los usuarios y sesiones DEMO no funcionan en LIVE. No hay cambio silencioso a DEMO ante errores.

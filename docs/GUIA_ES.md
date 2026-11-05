# Guía de Evidence Desk

Requisitos para DEMO: Git, Docker con Compose v2 y el puerto 3101 disponible. Clone con `git clone https://github.com/giovannyTorres/evidence-desk.git`, entre con `cd evidence-desk` y ejecute `docker compose up --build -d --wait` (o `make demo` si tiene Make). Abra http://localhost:3101. No necesita API keys, archivo `.env`, Python ni Node instalados en el equipo. Usuario Aurora: `analyst@aurora.example`; contraseña pública de demostración: `demo-evidence`. Meridian usa `analyst@meridian.example`. El indicador DEMO permanece visible.

Seleccione una pregunta sugerida, espere la respuesta y abra su cita para verificar documento, versión, sección y fragmento original. En Biblioteca puede cargar PDF con texto, TXT o Markdown, actualizar una versión, reintentar su procesamiento y eliminar un documento con confirmación. La extracción, persistencia, permisos y worker funcionan sin API keys. La búsqueda textual se identifica como tal. Una pregunta libre necesita LIVE; los ejemplos no pretenden interpretar texto arbitrario.

Las dos organizaciones son ficticias y sus manuales originales son sintéticos. No son políticas de una institución real. Las respuestas DEMO están ligadas al hash del manual original; si reemplaza ese contenido, el ejemplo se abstiene. Al eliminar el documento se eliminan índices y vínculos de citas correspondientes.

Para detener sin perder documentos ni conversaciones, ejecute `docker compose down`; para reanudar, `docker compose up -d --wait`. `docker compose ps` muestra los servicios y `docker compose logs --tail=40 api worker` permite revisar errores. No use `down -v` salvo que quiera eliminar los datos. Las migraciones y los manuales iniciales se preparan automáticamente.

Comprobación rápida desde el código: instale Python 3.12, uv 0.13.4, Node 22.18+ y Make; ejecute `make install` y `make quickcheck`. Reutiliza las pruebas de contratos de los SDK y las pruebas unitarias de la interfaz, sin base de datos, aplicación activa ni credenciales. La [sección de validación del README](../README.md#local-development-and-full-validation) explica cómo crear una base de pruebas aislada y ejecutar `make check types test build`. Para navegador sobre una aplicación DEMO ya activa: `WEB_URL=http://localhost:3101 npm --prefix apps/web run test:e2e`, tras instalar Chromium como indica el README. Las capturas en `docs/screenshots` provienen del navegador real. Los contratos de OpenAI y Gemini se verificaron con transportes simulados; no se enviaron llamadas pagadas. Las métricas de calidad de modelos y el despliegue Azure están pendientes.

Para LIVE siga [live.md](live.md): configure las claves solo en backend, cree un usuario LIVE mediante el comando de provisión, cargue documentos para indexar y ejecute el smoke test opcional. Los usuarios y sesiones DEMO no funcionan en LIVE. No hay cambio silencioso a DEMO ante errores.


## Auditoría técnica de la candidata

La evidencia actual está en [audit.md](audit.md): los resultados anteriores se conservan como registro histórico. Las pruebas usan exclusivamente `TEST_DATABASE_URL` con un nombre terminado en `_test`; no reutilizan la base configurada para la aplicación. El PDF se valida superficialmente al subirlo y se extrae en un subproceso del worker con límites Linux de memoria, CPU y tiempo. Un PDF dañado pasa a estado de error persistente y permite reintentar o eliminarlo. Un corte del streaming se informa como error recuperable, nunca como respuesta completa.

Para repetir una instalación aislada use el proyecto Compose `audit-evidence` y `infra/compose.audit.yaml` descritos en el informe. Conserva intactos los volúmenes originales y usa el puerto web 3201. Las verificaciones de contratos OpenAI/Gemini son transportes simulados; no equivalen a llamadas LIVE, calidad del modelo ni un despliegue Azure.

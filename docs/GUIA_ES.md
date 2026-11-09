# Guía de Evidence Desk

## Resumen del producto

- **Qué es:** un espacio para consultar políticas y procedimientos donde cada respuesta enlaza al documento, versión y fragmento exactos de los que proviene.
- **Para quién:** un analista que debe responder preguntas sobre documentos extensos y justificar su respuesta ante otra persona.
- **Problema que resuelve:** revisar manuales a mano es lento y una respuesta sin fuente es difícil de comprobar. La respuesta y su evidencia viajan juntas, el sistema se abstiene si no hay evidencia y cada organización solo ve sus documentos.
- **Qué es simulado:** en DEMO el **texto de la respuesta es un ejemplo predefinido**, etiquetado *Example response*. La cita no es simulada: es una consulta real a PostgreSQL limitada a la organización activa y al hash exacto del documento. Las preguntas libres requieren LIVE.
- **Qué requiere un proveedor real:** LIVE con OpenAI o Gemini y embeddings de OpenAI (claves de API). No se ha verificado ninguna llamada real.
- **Límites:** datos sintéticos, sin SSO, sin OCR, sin métricas de calidad de modelo. La abstención en LIVE depende del modelo: la PR #1 (borrador) observó un caso en que el modelo respondió con evidencia propia de Meridian en lugar de abstenerse, **sin recuperar ni citar fragmentos de Aurora**; no es una filtración y la corrección propuesta no está verificada.

**Recorrido de dos minutos:** (1) *Open workspace* con la cuenta Aurora; (2) *Document library* para ver los cuatro manuales; (3) pregunta *What is the daily domestic meal allowance?* y abrir la cita (Aurora Travel Handbook · Version 1 · Meals); (4) nueva conversación, *Explore 3 more example questions* → *What is the approved annual procurement budget?* para ver la falta de evidencia; (5) escribir una pregunta libre para ver el aviso de LIVE; (6) cerrar sesión, elegir *Meridian Studio*, preguntar *What is Meridian Studio's daily meal limit?* (420 MXN, fuente propia) y luego la pregunta de Aurora, que se rechaza.

**Windows 11:** el repositorio fija los manuales DEMO con finales de línea LF (`.gitattributes`) y la carga inicial normaliza CRLF, porque las respuestas DEMO dependen del hash exacto del manual. Un clon normal funciona con cualquier `core.autocrlf`.

## Instalación y uso

Requisitos para DEMO: Git, Docker con Compose v2 y el puerto 3101 disponible. Clone con `git clone https://github.com/giovannyTorres/evidence-desk.git`, entre con `cd evidence-desk` y ejecute `docker compose up --build -d --wait` (o `make demo` si tiene Make). Abra http://localhost:3101. No necesita API keys, archivo `.env`, Python ni Node instalados en el equipo. Usuario Aurora: `analyst@aurora.example`; contraseña pública de demostración: `demo-evidence`. Meridian usa `analyst@meridian.example`. El indicador DEMO permanece visible.

Seleccione una pregunta sugerida, espere la respuesta y abra su cita para verificar documento, versión, sección y fragmento original. En Biblioteca puede cargar PDF con texto, TXT o Markdown, actualizar una versión, reintentar su procesamiento y eliminar un documento con confirmación. La extracción, persistencia, permisos y worker funcionan sin API keys. La búsqueda textual se identifica como tal. Una pregunta libre necesita LIVE; los ejemplos no pretenden interpretar texto arbitrario.

Las dos organizaciones son ficticias y sus manuales originales son sintéticos. No son políticas de una institución real. Las respuestas DEMO están ligadas al hash del manual original; si reemplaza ese contenido, el ejemplo se abstiene. Al eliminar el documento se eliminan índices y vínculos de citas correspondientes.

Para detener sin perder documentos ni conversaciones, ejecute `docker compose down`; para reanudar, `docker compose up -d --wait`. `docker compose ps` muestra los servicios y `docker compose logs --tail=40 api worker` permite revisar errores. No use `down -v` salvo que quiera eliminar los datos. Las migraciones y los manuales iniciales se preparan automáticamente.

Comprobación rápida desde el código: instale Python 3.12, uv 0.13.4, Node 22.18+ y Make; ejecute `make install` y `make quickcheck`. Reutiliza las pruebas de contratos de los SDK y las pruebas unitarias de la interfaz, sin base de datos, aplicación activa ni credenciales. La [sección de validación del README](../README.md#local-development-and-full-validation) explica cómo crear una base de pruebas aislada y ejecutar `make check types test build`. Para navegador sobre una aplicación DEMO ya activa: `WEB_URL=http://localhost:3101 npm --prefix apps/web run test:e2e`, tras instalar Chromium como indica el README. Las capturas en `docs/screenshots` provienen del navegador real. Los contratos de OpenAI y Gemini se verificaron con transportes simulados; no se enviaron llamadas pagadas. Las métricas de calidad de modelos y el despliegue Azure están pendientes.

Para LIVE siga [live.md](live.md): configure las claves solo en backend, cree un usuario LIVE mediante el comando de provisión, cargue documentos para indexar y ejecute el smoke test opcional. Los usuarios y sesiones DEMO no funcionan en LIVE. No hay cambio silencioso a DEMO ante errores.


## Auditoría técnica de la candidata

La evidencia actual está en [audit.md](audit.md): los resultados anteriores se conservan como registro histórico. Las pruebas usan exclusivamente `TEST_DATABASE_URL` con un nombre terminado en `_test`; no reutilizan la base configurada para la aplicación. El PDF se valida superficialmente al subirlo y se extrae en un subproceso del worker con límites Linux de memoria, CPU y tiempo. Un PDF dañado pasa a estado de error persistente y permite reintentar o eliminarlo. Un corte del streaming se informa como error recuperable, nunca como respuesta completa.

Para repetir una instalación aislada use el proyecto Compose `audit-evidence` y `infra/compose.audit.yaml` descritos en el informe. Conserva intactos los volúmenes originales y usa el puerto web 3201. Las verificaciones de contratos OpenAI/Gemini son transportes simulados; no equivalen a llamadas LIVE, calidad del modelo ni un despliegue Azure.

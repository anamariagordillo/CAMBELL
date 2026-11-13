# Cambell (version Django) - Fase 1

Migracion de Cambell de Java/Spring Boot a Python/Django. Esta fase usa el diseno y las reglas
de la version mas reciente del proyecto (la que corre en el puerto 8080).

## Que incluye la fase 1
- Proyecto Django con configuracion por `.env` (SQLite por defecto, MySQL/MariaDB opcional).
- Diseno real de Cambell: tema claro/oscuro, inicio, login con carrusel, barras de navegacion por rol.
- Usuario propio con login por correo y 4 roles (CLIENTE, TRABAJADOR, ADMINISTRADOR, ALIADO_COMERCIAL).
- Registro en tres pasos para cliente, trabajador y aliado comercial, con terminos y habeas data,
  confirmacion de contrasena y validacion de archivos (extension y tipo).
- 15 modelos de la version Java, repartidos en apps (usuarios, solicitudes, pagos, mensajeria,
  anuncios, seguridad). Incluye el nuevo `DispositivoNotificacion` (tokens FCM).
- Catalogo de 12 localidades y 60 barrios de Bogota.
- Panel de gestion de Django en `/django-admin/` (solo rol ADMINISTRADOR).
- Pruebas automaticas de cada fase (`python manage.py test`).

## Fase 1A: autenticacion y cuenta
- Recuperar y restablecer contrasena con token de un solo uso.
- Cambiar contrasena y cambio obligatorio si no cumple la politica vigente.
- Bloqueo temporal por intentos fallidos (5 intentos / 15 minutos, configurable).
- Mi perfil, editar datos, cobertura del trabajador y desactivar cuenta.

## Fase 1B: modelos agregados
- `Horario`: bloques de disponibilidad semanal del trabajador (dia, hora de inicio,
  hora de fin y si esta activo). Complementa `CoberturaTrabajador`, que conserva la
  ventana general. Cubre la historia HU-T10.
- `Archivo`: registro general de archivos sensibles con nombre original, tipo MIME,
  tamano, hash SHA-256, version, vigencia y marca de cifrado. Es la base para cifrar,
  limpiar y versionar archivos (HU-S21, HU-S22 y HU-S23). Se mantiene
  `DocumentoVersion` como historial especifico del documento y la selfie.
- `Verificacion`: expediente de cada intento de verificacion de identidad, con estado,
  origen (automatica o manual), porcentaje de coincidencia, archivos, motivo, revisor
  y fechas. Cubre HU-T04, HU-T05, HU-A01 y HU-S10. `Usuario.estado_verificacion`
  sigue siendo el estado actual; `Verificacion` conserva el historial.
- `Trabajo`: no se crea como modelo. Un trabajo es una `Solicitud` con trabajador
  asignado; el historial laboral se consulta filtrando `Solicitud` por trabajador,
  estado y fecha. Asi no se duplica la misma informacion en dos tablas.

## Fase 1C: CRUD y pantallas
- Mensajeria: chat por solicitud entre cliente y trabajador, con aviso automatico a la
  contraparte; bandeja de notificaciones con filtros por tipo, paginacion, marcar como
  leida, marcar todas y eliminar.
- Anuncios del aliado comercial: listar, publicar, editar y eliminar. Toda edicion
  vuelve a estado `PENDIENTE` y el administrador aprueba o rechaza con motivo.
- Suscripcion premium simulada del trabajador: contratar, ver vencimiento y cancelar la
  renovacion automatica. El costo y la probabilidad de aprobacion se configuran en
  `.env`; por defecto el pago siempre se aprueba.
- Reportes de seguridad: el cliente reporta al trabajador y el trabajador al cliente
  dentro de una solicitud. El administrador puede bloquear al reportado o descartar el
  reporte.
- Verificacion: reintento con documento y selfie, y actualizacion de documento
  renovado. Ambos quedan `PENDIENTE` y registran un `Verificacion` y sus `Archivo`.
  La comparacion facial automatica se agrego en la Fase 1D (patron Strategy).
- Panel del administrador: moderacion de anuncios, reembolsos simulados de pagos
  completados y bandeja de reportes de seguridad. Las estadisticas se agregaron en la 1E.
- El aliado comercial ahora entra directo a `/anuncios/mios` al iniciar sesion.

## Fase 1D: patrones y tareas programadas
- **Strategy** para la verificacion de identidad (`usuarios/estrategias_verificacion.py`):
  - `VerificacionFacePlusPlus` compara documento y selfie con la API de Face++ y
    devuelve un porcentaje. Solo se usa si `FACEPP_API_KEY` y `FACEPP_API_SECRET`
    estan definidos; no es obligatoria.
  - `VerificacionManual` es la estrategia por defecto: deja el intento `PENDIENTE`
    para que un administrador lo revise. El proyecto funciona sin APIs externas.
  - `usuarios/verificacion_facial.py` aplica el umbral (`UMBRAL_VERIFICACION_FACIAL`),
    actualiza `Usuario.estado_verificacion` y guarda el expediente `Verificacion` con
    sus `Archivo`. El registro de trabajador y el reintento ya lo usan.
- **Observer** (`solicitudes/observadores.py`): al crearse o reasignarse una solicitud
  se avisa a los trabajadores aprobados y disponibles cuya cobertura encaja, ordenados
  del mas cercano al mas lejano. Tambien avisa al cliente cuando la aceptan o completan,
  y recalcula el promedio del trabajador al calificar.
- **Cobertura** (`usuarios/cobertura.py`): disponibilidad, horario (bloques de `Horario`
  o ventana general), especialidad, localidad y radio con distancia Haversine (km).
  Es la base que reutilizara el motor de recomendacion de la Fase 2.
- **Suscripcion y pagos**: renovacion automatica de suscripciones vencidas, aviso de las
  proximas a vencer y transferencia simulada de los netos a los trabajadores.
- **9 trabajos programados** (`tareas/trabajos.py`, app `tareas`): reasignar, cerrar no
  atendidas, avisar documentos, suspender cuentas reportadas, recordar calificaciones,
  renovar suscripciones, avisar suscripciones, transferir pagos y limpiar archivos.
  La limpieza borra solo archivos fisicos obsoletos y nunca uno que use un perfil.
- Se ejecutan sin Celery, con el comando `tareas_programadas`.

## Fase 1E: reporte multicriterio y estadisticas
- Pantalla `/admin/estadisticas` (nombre de URL `panel_admin:estadisticas`) con
  filtros combinables por rol, estado de solicitud, estado de pago y rango de fechas
  (`desde`/`hasta`). Los filtros se pueden limpiar sin perder la pantalla.
- Catorce tarjetas con los mismos indicadores del reporte Java: usuarios, clientes,
  trabajadores, aliados, solicitudes por estado, pagos, ingresos brutos, comision,
  anuncios pendientes y reportes en revision.
- Graficas de solicitudes por estado, usuarios por rol y serie mensual de solicitudes
  e ingresos. Si Chart.js (CDN) no carga, la pantalla sigue mostrando las tablas con
  los mismos datos.
- Exportacion a PDF (`/admin/estadisticas/exportar/pdf`) con marca, filtros,
  indicadores, solicitudes por estado, usuarios por rol y serie mensual.
- Exportacion a Excel (`/admin/estadisticas/exportar/excel`) con hoja `Resumen`
  (indicadores y serie mensual) y hoja `Detalle solicitudes` (una fila por solicitud
  filtrada). Ambas exportaciones conservan los filtros de la pantalla.
- Reglas de fechas: usuarios por `fecha_registro`; solicitudes y anuncios por
  `fecha_creacion`; pagos por `fecha_pago`; reportes por `fecha`. Sin filtro de estado
  de pago solo se usan los pagos `COMPLETADO` para ingresos y comision (si se filtra un
  estado, se respeta ese estado, igual que en Java).
- Codigo en `panel_admin/estadisticas.py`; pruebas en
  `panel_admin/test_estadisticas.py` (calculos, filtros, permisos, PDF, Excel y errores).

## Puesta en marcha (macOS, Terminal)
```bash
cd cambell_django
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env

python manage.py makemigrations usuarios solicitudes pagos mensajeria anuncios seguridad
python manage.py migrate
python manage.py crear_admin
python manage.py seed
python manage.py tareas_programadas --listar
python manage.py test
python manage.py runserver
```
Abre http://127.0.0.1:8000/  (la version Java usa el 8080; esta usa el 8000).
Si un comando muestra un error, copia el mensaje completo.

### Tareas programadas en produccion
En Java corrian con `@Scheduled`; aqui se ejecutan con el comando y se programan con
`cron` (o el Programador de tareas de Windows). Ejemplo para cada hora y una vez al dia:

```cron
# Reasignar solicitudes sin respuesta cada hora
30 * * * * cd /ruta/a/CAMBELL && .venv/bin/python manage.py tareas_programadas --tarea reasignar
# Documentos, suscripciones y limpieza: todos los dias a las 06:00
0 6 * * * cd /ruta/a/CAMBELL && .venv/bin/python manage.py tareas_programadas
```

Sin `--tarea` se ejecutan las 9 tareas. Los umbrales y horarios se configuran en `.env`.

## Barra de navegacion que se completa sola
`usuarios/contexto.py` define los enlaces de cada rol por NOMBRE de URL. Si la pantalla aun
no existe, el enlace no aparece; al crearla en una fase siguiente aparece sin tocar nada mas.
Nombres que usaran las fases siguientes:
- Cliente: solicitudes:nueva, solicitudes:mis_solicitudes, solicitudes:historial_cliente,
  pagos:metodos, pagos:historial, mensajeria:notificaciones
- Trabajador: solicitudes:disponibles, solicitudes:mis_trabajos, solicitudes:historial_trabajos,
  pagos:ingresos, usuarios:cobertura, pagos:suscripcion, mensajeria:notificaciones
- Aliado: anuncios:mios
- Administrador: panel_admin:verificaciones, usuarios, reportes, reembolsos, anuncios, estadisticas

## Cambios respecto a la version Java
- La contrasena del administrador ya no esta fija en el codigo: se pide con `crear_admin`.
- Los documentos, selfies y documentos legales NO se sirven por URL publica (en Java `/uploads/**`
  era publico). Solo las imagenes de anuncios son publicas. Se veran desde una vista protegida (fase 4).
- Dinero con `DecimalField` en vez de `Double`; fechas con zona horaria America/Bogota.
- El panel de Django queda en `/django-admin/` para dejar `/admin/...` libre para tus pantallas.
- El correo se guarda y se compara en minusculas.
- En el registro, los campos opcionales (barrio, tarifa, descripcion) ya no se vuelven obligatorios
  en el navegador (en Java el script los marcaba como `required`).
- Si el servidor devuelve errores, el formulario vuelve al paso 1 y pide escribir otra vez la
  contrasena (antes quedaba en un paso oculto con un campo obligatorio vacio).
- Nuevos campos para la IA de recomendacion en `Solicitud`: `urgencia`, `resumen_ia`, `confianza_ia`.

## Pendiente de fases siguientes
- Fase 2: motor de recomendacion con reglas + scikit-learn, pesos en settings, top 3 y
  comando `entrenar_clasificador`.
- Fases posteriores: antecedentes y cifrado de documentos, notificaciones push (FCM),
  antecedentes y revision de la integracion con Face++ cuando haya credenciales.

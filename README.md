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
- Pruebas automaticas en `usuarios/tests.py`.

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
python manage.py test
python manage.py runserver
```
Abre http://127.0.0.1:8000/  (la version Java usa el 8080; esta usa el 8000).
Si un comando muestra un error, copia el mensaje completo.

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
2 solicitudes, calificaciones (Observer), rechazo y reasignacion - 3 pagos simulados, comision 3 %,
reembolsos, suscripcion, ingresos - 4 verificacion Face++ (Strategy), documentos cifrados,
antecedentes - 5 mensajes, notificaciones y push (FCM), anuncios, reportes, recuperar y cambiar
contrasena (`debe_cambiar_password`), tareas programadas - 6 panel de administrador
(verificaciones, usuarios, estadisticas, PDF y Excel) - IA de recomendacion (reglas + scikit-learn).

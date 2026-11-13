import hashlib
import os
from datetime import time

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone

from .validadores import validar_extension


class Rol(models.TextChoices):
    CLIENTE = "CLIENTE", "Cliente"
    TRABAJADOR = "TRABAJADOR", "Trabajador"
    ADMINISTRADOR = "ADMINISTRADOR", "Administrador"
    ALIADO_COMERCIAL = "ALIADO_COMERCIAL", "Aliado comercial"


class EstadoVerificacion(models.TextChoices):
    PENDIENTE = "PENDIENTE", "Pendiente"
    APROBADO = "APROBADO", "Aprobado"
    RECHAZADO = "RECHAZADO", "Rechazado"


validar_nit = RegexValidator(r"^[0-9]{6,15}$", "El NIT debe tener solo números (6 a 15 dígitos)")

validar_documento = RegexValidator(
    r"^[0-9]{6,15}$", "El documento debe tener solo números (6 a 15 dígitos)"
)
validar_telefono = RegexValidator(
    r"^[0-9]{7,15}$", "El teléfono debe tener solo números (7 a 15 dígitos)"
)


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _crear(self, correo, password, **extra):
        if not correo:
            raise ValueError("El correo es obligatorio")
        correo = self.normalize_email(correo)
        usuario = self.model(correo=correo, **extra)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, correo, password=None, **extra):
        extra.setdefault("rol", Rol.CLIENTE)
        return self._crear(correo, password, **extra)

    def create_superuser(self, correo, password=None, **extra):
        extra["rol"] = Rol.ADMINISTRADOR
        extra["is_superuser"] = True
        extra.setdefault("estado_verificacion", EstadoVerificacion.APROBADO)
        return self._crear(correo, password, **extra)


class Usuario(AbstractBaseUser, PermissionsMixin):
    nombre = models.CharField(max_length=100)
    correo = models.EmailField(unique=True)
    rol = models.CharField(max_length=20, choices=Rol.choices)

    estado_verificacion = models.CharField(
        max_length=20, choices=EstadoVerificacion.choices, default=EstadoVerificacion.PENDIENTE
    )
    motivo_verificacion = models.CharField(max_length=500, blank=True)
    calificacion_promedio = models.FloatField(default=0.0)
    total_calificaciones = models.PositiveIntegerField(default=0)

    # Verificacion de identidad (trabajadores)
    numero_documento = models.CharField(
        max_length=15, unique=True, null=True, blank=True, validators=[validar_documento]
    )
    documento = models.FileField(
        upload_to="documentos/", null=True, blank=True, validators=[validar_extension]
    )
    selfie = models.FileField(
        upload_to="selfies/", null=True, blank=True, validators=[validar_extension]
    )
    fecha_vencimiento_documento = models.DateField(null=True, blank=True)
    antecedentes = models.TextField(max_length=2000, blank=True)
    fecha_consulta_antecedentes = models.DateTimeField(null=True, blank=True)

    # Contacto y ubicacion (clientes y aliados)
    telefono = models.CharField(
        max_length=15, unique=True, null=True, blank=True, validators=[validar_telefono]
    )
    localidad = models.CharField(max_length=100, blank=True)
    barrio = models.CharField(max_length=100, blank=True)

    # Perfil del trabajador
    oficio = models.CharField(max_length=100, null=True, blank=True)
    anios_experiencia = models.PositiveSmallIntegerField(null=True, blank=True)
    tarifa_hora = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    cuenta_bancaria = models.CharField(max_length=255, null=True, blank=True)
    bio = models.TextField(max_length=2000, blank=True)
    foto_perfil = models.FileField(
        upload_to="perfiles/", null=True, blank=True, validators=[validar_extension]
    )

    # Aliado comercial
    razon_social = models.CharField(max_length=200, null=True, blank=True)
    nit = models.CharField(max_length=15, unique=True, null=True, blank=True, validators=[validar_nit])
    tipo_aliado = models.CharField(max_length=100, null=True, blank=True)
    direccion_negocio = models.CharField(max_length=255, null=True, blank=True)
    documento_legal = models.FileField(
        upload_to="legales/", null=True, blank=True, validators=[validar_extension]
    )

    # Consentimientos (habeas data, Ley 1581 de 2012)
    acepta_terminos = models.BooleanField(default=False)
    acepta_datos = models.BooleanField(default=False)

    bloqueado = models.BooleanField(default=False)
    # Se activa cuando la contrasena no cumple la politica vigente (fase 5: /cambiar-password)
    debe_cambiar_password = models.BooleanField(default=False)

    # Bloqueo temporal por intentos fallidos de inicio de sesion.
    # No se confunde con `bloqueado`, que es el bloqueo manual del administrador.
    intentos_fallidos = models.PositiveSmallIntegerField(default=0)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)

    fecha_registro = models.DateTimeField(default=timezone.now)

    objects = UsuarioManager()

    USERNAME_FIELD = "correo"
    REQUIRED_FIELDS = ["nombre"]

    class Meta:
        db_table = "usuarios"
        ordering = ["id"]

    def __str__(self):
        return f"{self.nombre} <{self.correo}>"

    # Django usa is_active para impedir el login: un usuario bloqueado no entra.
    @property
    def is_active(self):
        return not self.bloqueado

    # El panel /admin/ de Django solo es para el rol ADMINISTRADOR.
    @property
    def is_staff(self):
        return self.rol == Rol.ADMINISTRADOR

    @property
    def es_trabajador(self):
        return self.rol == Rol.TRABAJADOR

    @property
    def esta_verificado(self):
        return self.estado_verificacion == EstadoVerificacion.APROBADO

    @property
    def bloqueo_temporal_activo(self):
        """True mientras dure el castigo por escribir mal la contrasena varias veces."""
        return bool(self.bloqueado_hasta and self.bloqueado_hasta > timezone.now())

    def minutos_de_bloqueo(self):
        """Minutos que le faltan al bloqueo temporal (para el mensaje al usuario)."""
        if not self.bloqueo_temporal_activo:
            return 0
        restante = self.bloqueado_hasta - timezone.now()
        # Se redondea hacia arriba para no decir "0 minutos" cuando faltan segundos.
        return max(1, int(restante.total_seconds() // 60) + 1)


class DocumentoVersion(models.Model):
    """Historial de versiones del documento y la selfie de un trabajador."""

    class Tipo(models.TextChoices):
        DOCUMENTO = "DOCUMENTO", "Documento"
        SELFIE = "SELFIE", "Selfie"

    trabajador = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name="documentos_version"
    )
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    archivo = models.FileField(upload_to="versiones/")
    version = models.PositiveIntegerField(default=1)
    vigente = models.BooleanField(default=True)
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "documentos_version"
        ordering = ["-fecha"]


class CoberturaTrabajador(models.Model):
    """Zona, oficios y disponibilidad del trabajador (la usa el motor de recomendacion)."""

    trabajador = models.OneToOneField(
        Usuario, on_delete=models.CASCADE, related_name="cobertura"
    )
    radio_km = models.FloatField(default=10.0)
    localidades = models.JSONField(default=list, blank=True)
    categorias = models.JSONField(default=list, blank=True)
    disponible = models.BooleanField(default=True)
    hora_inicio = models.TimeField(default=time(8, 0))
    hora_fin = models.TimeField(default=time(18, 0))

    class Meta:
        db_table = "cobertura_trabajador"


class Horario(models.Model):
    """Bloque de disponibilidad semanal de un trabajador (HU-T10).

    Un trabajador puede tener varios bloques por dia (por ejemplo 8:00-12:00 y
    14:00-18:00). `CoberturaTrabajador` sigue guardando la ventana general que ya
    usaba la Fase 1; este modelo detalla los dias y las horas.
    """

    class Dia(models.IntegerChoices):
        # Se usa el mismo numero que date.weekday(): 0 = lunes, 6 = domingo.
        LUNES = 0, "Lunes"
        MARTES = 1, "Martes"
        MIERCOLES = 2, "Miércoles"
        JUEVES = 3, "Jueves"
        VIERNES = 4, "Viernes"
        SABADO = 5, "Sábado"
        DOMINGO = 6, "Domingo"

    trabajador = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name="horarios"
    )
    dia_semana = models.PositiveSmallIntegerField(choices=Dia.choices)
    hora_inicio = models.TimeField(default=time(8, 0))
    hora_fin = models.TimeField(default=time(18, 0))
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "horarios_trabajador"
        ordering = ["trabajador_id", "dia_semana", "hora_inicio"]
        constraints = [
            # No se repite el mismo bloque para el mismo trabajador y dia.
            models.UniqueConstraint(
                fields=["trabajador", "dia_semana", "hora_inicio", "hora_fin"],
                name="horario_unico_por_bloque",
            ),
            # La base de datos tambien impide guardar un horario al reves.
            models.CheckConstraint(
                condition=models.Q(hora_fin__gt=models.F("hora_inicio")),
                name="horario_hora_fin_mayor",
            ),
        ]

    def clean(self):
        super().clean()
        if self.hora_inicio and self.hora_fin and self.hora_fin <= self.hora_inicio:
            raise ValidationError(
                {"hora_fin": "La hora de fin debe ser posterior a la hora de inicio."}
            )

    def cubre(self, momento=None):
        """True si este bloque cubre el dia y la hora indicados.

        Si no se pasa un momento, se usa la fecha y hora actual de Bogota.
        """
        momento = momento or timezone.localtime()
        if not self.activo or self.dia_semana != momento.weekday():
            return False
        return self.hora_inicio <= momento.time() <= self.hora_fin

    def __str__(self):
        return (
            f"{self.get_dia_semana_display()} "
            f"{self.hora_inicio:%H:%M}-{self.hora_fin:%H:%M}"
        )


class Archivo(models.Model):
    """Registro de archivos sensibles de la plataforma (HU-S21, S22 y S23).

    Guarda los datos que las fases siguientes necesitan para cifrar, limpiar y
    versionar archivos: hash SHA-256, tamano, tipo MIME, version y vigencia.
    `DocumentoVersion` se mantiene como el historial especifico del documento y
    la selfie de identidad; este modelo sera el registro general de archivos.
    """

    class Tipo(models.TextChoices):
        DOCUMENTO = "DOCUMENTO", "Documento de identidad"
        SELFIE = "SELFIE", "Selfie"
        DOCUMENTO_LEGAL = "DOCUMENTO_LEGAL", "Documento legal"
        EVIDENCIA = "EVIDENCIA", "Evidencia de un servicio"
        ANUNCIO = "ANUNCIO", "Imagen de un anuncio"
        OTRO = "OTRO", "Otro"

    propietario = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name="archivos"
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    archivo = models.FileField(upload_to="archivos/%Y/%m/", validators=[validar_extension])
    nombre_original = models.CharField(max_length=255, blank=True)
    mime = models.CharField(max_length=100, blank=True)
    tamano_bytes = models.PositiveBigIntegerField(default=0)
    # Huella del contenido: sirve para detectar archivos repetidos o alterados.
    hash_sha256 = models.CharField(max_length=64, blank=True)
    cifrado = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)
    vigente = models.BooleanField(default=True)
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "archivos"
        ordering = ["-fecha"]

    def calcular_hash(self):
        """Calcula el SHA-256 del archivo y deja el puntero al inicio."""
        resumen = hashlib.sha256()
        self.archivo.open("rb")
        self.archivo.seek(0)
        for bloque in iter(lambda: self.archivo.read(8192), b""):
            resumen.update(bloque)
        self.archivo.seek(0)
        return resumen.hexdigest()

    def calcular_tamano(self):
        """Mide el archivo sin cargarlo completo en memoria."""
        posicion = self.archivo.tell()
        self.archivo.seek(0, os.SEEK_END)
        tamano = self.archivo.tell()
        self.archivo.seek(posicion)
        return tamano

    def save(self, *args, **kwargs):
        """Completa solo los datos que falten (nombre, tamano y hash)."""
        if self.archivo:
            self.nombre_original = self.nombre_original or os.path.basename(self.archivo.name)
            try:
                if not self.tamano_bytes:
                    self.tamano_bytes = self.calcular_tamano()
                if not self.hash_sha256:
                    self.hash_sha256 = self.calcular_hash()
            except (OSError, ValueError):
                # Si el archivo no esta disponible, se guarda el registro sin esos datos.
                pass
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_tipo_display()} de {self.propietario.nombre}"


class Verificacion(models.Model):
    """Expediente de cada intento de verificacion de identidad.

    `Usuario.estado_verificacion` guarda solo el estado actual. Este modelo
    conserva el historial que piden las historias HU-T04, HU-T05, HU-A01 y
    HU-S10: que se comparo, con que porcentaje, con que origen y quien decidio.
    """

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        APROBADA = "APROBADA", "Aprobada"
        RECHAZADA = "RECHAZADA", "Rechazada"
        REVISION_MANUAL = "REVISION_MANUAL", "Requiere revisión manual"

    class Origen(models.TextChoices):
        AUTOMATICA = "AUTOMATICA", "Automática"
        MANUAL = "MANUAL", "Manual"

    trabajador = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name="verificaciones"
    )
    estado = models.CharField(
        max_length=20, choices=Estado.choices, default=Estado.PENDIENTE
    )
    origen = models.CharField(
        max_length=10, choices=Origen.choices, default=Origen.AUTOMATICA
    )
    porcentaje_coincidencia = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Resultado de la comparacion facial (0 a 100).",
    )
    documento = models.ForeignKey(
        Archivo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verificaciones_documento",
    )
    selfie = models.ForeignKey(
        Archivo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verificaciones_selfie",
    )
    motivo = models.CharField(max_length=500, blank=True)
    revisor = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verificaciones_revisadas",
    )
    fecha_creacion = models.DateTimeField(default=timezone.now)
    fecha_decision = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "verificaciones"
        ordering = ["-fecha_creacion"]

    @property
    def aprobada(self):
        return self.estado == self.Estado.APROBADA

    def __str__(self):
        return (
            f"Verificación #{self.pk} de {self.trabajador.nombre} "
            f"({self.get_estado_display()})"
        )


class TokenRecuperacion(models.Model):
    usuario = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name="tokens_recuperacion"
    )
    token = models.CharField(max_length=100, unique=True)
    expiracion = models.DateTimeField()
    usado = models.BooleanField(default=False)

    class Meta:
        db_table = "tokens_recuperacion"

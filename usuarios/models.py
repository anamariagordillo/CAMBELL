from datetime import time

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
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


class TokenRecuperacion(models.Model):
    usuario = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name="tokens_recuperacion"
    )
    token = models.CharField(max_length=100, unique=True)
    expiracion = models.DateTimeField()
    usado = models.BooleanField(default=False)

    class Meta:
        db_table = "tokens_recuperacion"

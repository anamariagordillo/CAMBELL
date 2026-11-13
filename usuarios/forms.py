from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from solicitudes.models import CategoriaServicio

from .catalogos import OFICIOS, TIPOS_ALIADO
from .localidades import LOCALIDADES, nombres_localidades
from .models import CoberturaTrabajador, EstadoVerificacion, Rol, Usuario
from .politicas import MSG_PASSWORD, PATRON_PASSWORD
from .validadores import validar_mime

ROLES_REGISTRABLES = [
    ("", "Selecciona un rol"),
    (Rol.CLIENTE.value, "Cliente"),
    (Rol.TRABAJADOR.value, "Trabajador"),
    (Rol.ALIADO_COMERCIAL.value, "Aliado comercial"),
]


class LoginForm(AuthenticationForm):
    username = forms.EmailField(
        label="Correo",
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )
    password = forms.CharField(
        label="Contraseña",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    error_messages = {
        "invalid_login": "Correo o contraseña incorrectos. Intenta de nuevo.",
        "inactive": "Esta cuenta está desactivada.",
    }

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()

    def confirm_login_allowed(self, user):
        """Se ejecuta solo cuando el correo y la contrasena son correctos."""
        super().confirm_login_allowed(user)
        if user.bloqueo_temporal_activo:
            raise ValidationError(
                "Demasiados intentos fallidos. "
                f"Tu cuenta estará bloqueada {user.minutos_de_bloqueo()} minuto(s).",
                code="bloqueo_temporal",
            )


class RegistroForm(forms.ModelForm):
    """Registro en pasos para cliente, trabajador y aliado comercial.

    Reproduce las reglas de RegistroController.java. La plantilla dibuja los campos a mano
    (cada rol ve su propio bloque), por eso aquí los widgets son los de Django por defecto.
    """

    nombre = forms.CharField(
        label="Nombre completo", min_length=3, max_length=100,
        validators=[RegexValidator(r"^[A-Za-zÀ-ÿ\s]+$", "El nombre solo debe contener letras")],
    )
    correo = forms.EmailField(label="Correo")
    password = forms.CharField(
        label="Contraseña", min_length=8, max_length=64, strip=False,
        validators=[RegexValidator(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).+$", MSG_PASSWORD)],
    )
    confirm_password = forms.CharField(label="Confirmar contraseña", strip=False, required=False)
    rol = forms.ChoiceField(
        label="Rol", choices=ROLES_REGISTRABLES,
        error_messages={
            "required": "Debes seleccionar un rol",
            "invalid_choice": "Rol inválido: selecciona Cliente, Trabajador o Aliado comercial.",
        },
    )
    acepta_terminos = forms.BooleanField(
        required=True, error_messages={"required": "Debes aceptar los términos y condiciones."}
    )
    acepta_datos = forms.BooleanField(
        required=True,
        error_messages={"required": "Debes autorizar el tratamiento de tus datos personales."},
    )
    localidad = forms.ChoiceField(
        label="Localidad", required=False,
        choices=[("", "Selecciona tu localidad")] + [(n, n) for n in nombres_localidades()],
    )
    oficio = forms.ChoiceField(
        label="Oficio", required=False,
        choices=[("", "Selecciona tu oficio")] + [(o, o) for o in OFICIOS],
    )
    tipo_aliado = forms.ChoiceField(
        label="Tipo de aliado", required=False,
        choices=[("", "Selecciona un tipo")] + [(t, t) for t in TIPOS_ALIADO],
    )
    anios_experiencia = forms.IntegerField(
        label="Años de experiencia", required=False, min_value=0, max_value=60
    )

    class Meta:
        model = Usuario
        fields = [
            "nombre", "correo", "rol", "telefono", "localidad", "barrio",
            "oficio", "anios_experiencia", "tarifa_hora", "cuenta_bancaria", "bio",
            "foto_perfil", "numero_documento", "documento", "selfie",
            "razon_social", "nit", "tipo_aliado", "direccion_negocio", "documento_legal",
            "acepta_terminos", "acepta_datos",
        ]
        labels = {
            "telefono": "Teléfono", "barrio": "Barrio", "tarifa_hora": "Tarifa por hora",
            "cuenta_bancaria": "Datos para recibir pagos", "bio": "Descripción",
            "foto_perfil": "Foto de perfil", "numero_documento": "Número de documento",
            "documento": "Foto del documento", "selfie": "Selfie de verificación",
            "razon_social": "Razón social", "nit": "NIT",
            "direccion_negocio": "Dirección del negocio", "documento_legal": "Documento legal",
        }

    # ---- Archivos: extensión (modelo) + tipo MIME (aquí) ----
    def _mime(self, campo):
        archivo = self.cleaned_data.get(campo)
        if archivo:
            validar_mime(archivo)
        return archivo

    def clean_documento(self):
        return self._mime("documento")

    def clean_selfie(self):
        return self._mime("selfie")

    def clean_foto_perfil(self):
        return self._mime("foto_perfil")

    def clean_documento_legal(self):
        return self._mime("documento_legal")

    # ---- Datos ya en uso ----
    def clean_correo(self):
        correo = self.cleaned_data["correo"].strip().lower()
        if Usuario.objects.filter(correo__iexact=correo).exists():
            self.hay_duplicado = True
            raise ValidationError("Este correo ya está registrado. Inicia sesión o usa otro correo.")
        return correo

    def clean_telefono(self):
        telefono = self.cleaned_data.get("telefono") or None
        if telefono and Usuario.objects.filter(telefono=telefono).exists():
            self.hay_duplicado = True
            raise ValidationError("Este teléfono ya está registrado con otra cuenta.")
        return telefono

    hay_duplicado = False

    def _obligatorio(self, datos, campo, mensaje):
        valor = datos.get(campo)
        if valor is None or valor == "":
            self.add_error(campo, mensaje)

    # ---- Reglas por rol ----
    def clean(self):
        datos = super().clean()
        rol = datos.get("rol")

        pw, confirmar = datos.get("password"), datos.get("confirm_password")
        if "password" in datos:
            if not confirmar:
                self.add_error("confirm_password", "Debes confirmar la contraseña.")
            elif pw != confirmar:
                self.add_error("confirm_password", "Las contraseñas no coinciden.")

        if rol == Rol.TRABAJADOR:
            self._obligatorio(datos, "telefono", "El teléfono / WhatsApp de contacto es obligatorio")
            self._obligatorio(datos, "localidad", "Selecciona tu ciudad o zona de cobertura")
            self._obligatorio(datos, "oficio", "Selecciona tu oficio o especialidad")
            self._obligatorio(datos, "anios_experiencia", "Indica tus años de experiencia")
            self._obligatorio(datos, "cuenta_bancaria", "Los datos para recibir pagos son obligatorios")
            self._obligatorio(datos, "numero_documento", "El número de documento es obligatorio para trabajadores")
            self._obligatorio(datos, "documento", "Debes subir una foto de tu documento")
            self._obligatorio(datos, "selfie", "Debes subir una selfie de verificación")
            numero = datos.get("numero_documento")
            if numero and Usuario.objects.filter(numero_documento=numero).exists():
                self.hay_duplicado = True
                self.add_error("numero_documento", "Este número de documento ya está registrado con otra cuenta.")
            for campo in ("razon_social", "nit", "tipo_aliado", "direccion_negocio", "documento_legal"):
                datos[campo] = None
        elif rol == Rol.ALIADO_COMERCIAL:
            self._obligatorio(datos, "razon_social", "La razón social es obligatoria")
            self._obligatorio(datos, "nit", "El NIT es obligatorio para aliados comerciales")
            self._obligatorio(datos, "tipo_aliado", "Selecciona el tipo de aliado")
            self._obligatorio(datos, "telefono", "El teléfono / WhatsApp comercial es obligatorio")
            self._obligatorio(datos, "direccion_negocio", "La dirección del negocio es obligatoria")
            self._obligatorio(datos, "documento_legal",
                              "Debes subir el documento legal del negocio (RUT o cámara de comercio)")
            nit = datos.get("nit")
            if nit and Usuario.objects.filter(nit=nit).exists():
                self.hay_duplicado = True
                self.add_error("nit", "Este NIT ya está registrado con otra cuenta.")
            for campo in ("oficio", "anios_experiencia", "tarifa_hora", "cuenta_bancaria",
                          "numero_documento", "documento", "selfie"):
                datos[campo] = None
        elif rol == Rol.CLIENTE:
            self._obligatorio(datos, "telefono", "El teléfono de contacto es obligatorio")
            self._obligatorio(datos, "localidad", "Selecciona tu localidad")
            for campo in ("oficio", "anios_experiencia", "tarifa_hora", "cuenta_bancaria",
                          "numero_documento", "documento", "selfie",
                          "razon_social", "nit", "tipo_aliado", "direccion_negocio", "documento_legal"):
                datos[campo] = None
        return datos

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.set_password(self.cleaned_data["password"])
        # Cliente y aliado quedan activos; el trabajador pasa por verificación.
        if usuario.rol == Rol.TRABAJADOR:
            usuario.estado_verificacion = EstadoVerificacion.PENDIENTE
        else:
            usuario.estado_verificacion = EstadoVerificacion.APROBADO
        if commit:
            usuario.save()
            # Si subió documento y selfie, se intenta la verificación automática.
            # Sin credenciales de Face++ la estrategia es manual y queda PENDIENTE.
            if usuario.rol == Rol.TRABAJADOR and usuario.documento and usuario.selfie:
                from .verificacion_facial import evaluar_y_registrar

                evaluar_y_registrar(usuario)
        return usuario


# ============================================================ Cuenta y seguridad
class RecuperarPasswordForm(forms.Form):
    """Pide el correo para enviar el enlace de recuperacion."""

    correo = forms.EmailField(
        label="Correo registrado",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}),
    )

    def clean_correo(self):
        return self.cleaned_data["correo"].strip().lower()


class RestablecerPasswordForm(forms.Form):
    """Nueva contrasena, usando el token que llega en el enlace del correo."""

    token = forms.CharField(widget=forms.HiddenInput)
    password = forms.CharField(
        label="Nueva contraseña",
        min_length=8,
        max_length=64,
        strip=False,
        validators=[RegexValidator(PATRON_PASSWORD, MSG_PASSWORD)],
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    confirmar_password = forms.CharField(
        label="Confirmar contraseña",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean(self):
        datos = super().clean()
        nueva = datos.get("password")
        confirmar = datos.get("confirmar_password")
        if nueva and confirmar and nueva != confirmar:
            self.add_error("confirmar_password", "Las contraseñas no coinciden.")
        return datos


class CambiarPasswordForm(forms.Form):
    """Cambio de contrasena desde la cuenta.

    `forzado=True` se usa cuando el sistema obliga el cambio: no se pide la
    contrasena actual (puede estar vencida por la politica nueva).
    """

    password_actual = forms.CharField(
        label="Contraseña actual",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    password_nueva = forms.CharField(
        label="Nueva contraseña",
        min_length=8,
        max_length=64,
        strip=False,
        validators=[RegexValidator(PATRON_PASSWORD, MSG_PASSWORD)],
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    confirmar_password = forms.CharField(
        label="Confirmar contraseña",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args, usuario=None, forzado=False, **kwargs):
        self.usuario = usuario
        self.forzado = forzado
        super().__init__(*args, **kwargs)
        if forzado:
            self.fields["password_actual"].required = False
            self.fields["password_actual"].widget = forms.HiddenInput()

    def clean_password_actual(self):
        if self.forzado:
            return ""
        actual = self.cleaned_data.get("password_actual", "")
        if not self.usuario or not self.usuario.check_password(actual):
            raise ValidationError("La contraseña actual es incorrecta.")
        return actual

    def clean(self):
        datos = super().clean()
        nueva = datos.get("password_nueva")
        confirmar = datos.get("confirmar_password")
        if nueva and confirmar and nueva != confirmar:
            self.add_error("confirmar_password", "Las contraseñas no coinciden.")
        return datos


class PerfilForm(forms.ModelForm):
    """Datos basicos que el usuario puede cambiar de su propio perfil."""

    class Meta:
        model = Usuario
        fields = ["nombre", "correo", "telefono", "localidad", "barrio"]
        labels = {
            "nombre": "Nombre completo",
            "correo": "Correo",
            "telefono": "Teléfono",
            "localidad": "Localidad",
            "barrio": "Barrio",
        }

    def clean_correo(self):
        correo = self.cleaned_data["correo"].strip().lower()
        repetido = Usuario.objects.filter(correo__iexact=correo).exclude(pk=self.instance.pk)
        if repetido.exists():
            raise ValidationError("Este correo ya está registrado con otra cuenta.")
        return correo

    def clean_telefono(self):
        telefono = (self.cleaned_data.get("telefono") or "").strip()
        if not telefono:
            return None
        repetido = Usuario.objects.filter(telefono=telefono).exclude(pk=self.instance.pk)
        if repetido.exists():
            raise ValidationError("Este teléfono ya está registrado con otra cuenta.")
        return telefono


class CoberturaForm(forms.ModelForm):
    """Zona, oficios y horario en que trabaja un trabajador."""

    localidades = forms.MultipleChoiceField(
        label="Localidades de cobertura",
        required=False,
        choices=[(nombre, nombre) for nombre in LOCALIDADES],
        widget=forms.CheckboxSelectMultiple,
    )
    categorias = forms.MultipleChoiceField(
        label="Especialidades",
        required=False,
        choices=CategoriaServicio.choices,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = CoberturaTrabajador
        fields = ["radio_km", "localidades", "categorias", "disponible", "hora_inicio", "hora_fin"]
        labels = {
            "radio_km": "Radio de cobertura (km)",
            "disponible": "Estoy disponible ahora",
            "hora_inicio": "Hora de inicio",
            "hora_fin": "Hora de fin",
        }
        widgets = {
            "radio_km": forms.NumberInput(attrs={"min": 1, "max": 50, "step": "0.5"}),
            "hora_inicio": forms.TimeInput(attrs={"type": "time"}),
            "hora_fin": forms.TimeInput(attrs={"type": "time"}),
        }

    def clean_radio_km(self):
        radio = self.cleaned_data["radio_km"]
        if radio <= 0:
            raise ValidationError("El radio de cobertura debe ser mayor a 0 km.")
        if radio > 50:
            raise ValidationError("El radio de cobertura no puede superar 50 km.")
        return radio

    def clean(self):
        datos = super().clean()
        inicio = datos.get("hora_inicio")
        fin = datos.get("hora_fin")
        if inicio and fin and fin < inicio:
            self.add_error("hora_fin", "La hora de fin debe ser posterior a la hora de inicio.")
        return datos

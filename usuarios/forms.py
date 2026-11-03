from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from .catalogos import OFICIOS, TIPOS_ALIADO
from .localidades import nombres_localidades
from .models import EstadoVerificacion, Rol, Usuario
from .validadores import validar_mime

MSG_PASSWORD = "La contraseña debe tener al menos una mayúscula, una minúscula y un número"

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
        # (La verificación automática con Face++ se agrega en la fase 4.)
        if usuario.rol == Rol.TRABAJADOR:
            usuario.estado_verificacion = EstadoVerificacion.PENDIENTE
        else:
            usuario.estado_verificacion = EstadoVerificacion.APROBADO
        if commit:
            usuario.save()
        return usuario

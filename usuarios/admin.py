from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField

from .models import CoberturaTrabajador, DocumentoVersion, TokenRecuperacion, Usuario


class UsuarioCreationForm(forms.ModelForm):
    password1 = forms.CharField(label="Contraseña", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirmar contraseña", widget=forms.PasswordInput)

    class Meta:
        model = Usuario
        fields = ("correo", "nombre", "rol")

    def clean_password2(self):
        p1, p2 = self.cleaned_data.get("password1"), self.cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Las contraseñas no coinciden.")
        return p2

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.set_password(self.cleaned_data["password1"])
        if commit:
            usuario.save()
        return usuario


class UsuarioChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(
        label="Contraseña",
        help_text='Las contraseñas no se guardan en claro. Cámbiala con <a href="../password/">este formulario</a>.',
    )

    class Meta:
        model = Usuario
        fields = "__all__"


@admin.register(Usuario)
class UsuarioAdmin(BaseUserAdmin):
    form = UsuarioChangeForm
    add_form = UsuarioCreationForm
    list_display = ("id", "nombre", "correo", "rol", "estado_verificacion", "bloqueado")
    list_filter = ("rol", "estado_verificacion", "bloqueado")
    search_fields = ("nombre", "correo", "numero_documento", "telefono")
    ordering = ("id",)
    filter_horizontal = ("groups", "user_permissions")
    fieldsets = (
        (None, {"fields": ("correo", "password")}),
        ("Datos personales", {"fields": ("nombre", "rol", "telefono", "localidad", "barrio")}),
        ("Verificación de identidad", {"fields": (
            "estado_verificacion", "numero_documento", "documento", "selfie",
            "fecha_vencimiento_documento", "antecedentes", "fecha_consulta_antecedentes",
        )}),
        ("Reputación", {"fields": ("calificacion_promedio", "total_calificaciones")}),
        ("Acceso", {"fields": ("bloqueado", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("correo", "nombre", "rol", "password1", "password2")}),
    )


@admin.register(CoberturaTrabajador)
class CoberturaAdmin(admin.ModelAdmin):
    list_display = ("trabajador", "radio_km", "disponible", "hora_inicio", "hora_fin")


@admin.register(DocumentoVersion)
class DocumentoVersionAdmin(admin.ModelAdmin):
    list_display = ("trabajador", "tipo", "version", "vigente", "fecha")
    list_filter = ("tipo", "vigente")


admin.site.register(TokenRecuperacion)

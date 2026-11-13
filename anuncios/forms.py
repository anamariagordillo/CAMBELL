"""Formulario de anuncios del aliado comercial."""
from django import forms
from django.core.exceptions import ValidationError

from .models import Anuncio
from usuarios.validadores import validar_mime

TAMANO_MAXIMO = 5 * 1024 * 1024  # 5 MB, igual que el límite general de subidas


class AnuncioForm(forms.ModelForm):
    class Meta:
        model = Anuncio
        fields = ["titulo", "descripcion", "imagen"]
        widgets = {
            "titulo": forms.TextInput(attrs={"maxlength": 200, "required": True}),
            "descripcion": forms.Textarea(
                attrs={"rows": 4, "maxlength": 1000, "required": True}
            ),
            "imagen": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def clean_titulo(self):
        titulo = (self.cleaned_data.get("titulo") or "").strip()
        if not titulo:
            raise ValidationError("El título es obligatorio.")
        return titulo

    def clean_descripcion(self):
        descripcion = (self.cleaned_data.get("descripcion") or "").strip()
        if not descripcion:
            raise ValidationError("La descripción es obligatoria.")
        return descripcion

    def clean_imagen(self):
        imagen = self.cleaned_data.get("imagen")
        if imagen and getattr(imagen, "size", 0) > TAMANO_MAXIMO:
            raise ValidationError("La imagen no puede superar los 5 MB.")
        if imagen:
            validar_mime(imagen)
        return imagen

from django import forms

from usuarios.localidades import LOCALIDADES

from .models import CategoriaServicio


class FiltroDisponiblesForm(forms.Form):
    """Lee y limpia los filtros de la pantalla 'Solicitudes disponibles' (vienen por la URL)."""

    localidad = forms.ChoiceField(
        required=False, choices=[("", "Todas")] + [(n, n) for n in LOCALIDADES]
    )
    barrio = forms.CharField(required=False, max_length=100)
    categoria = forms.ChoiceField(
        required=False, choices=[("", "Todas")] + list(CategoriaServicio.choices)
    )
    precio_min = forms.DecimalField(required=False, min_value=0)
    precio_max = forms.DecimalField(required=False, min_value=0)
    orden = forms.ChoiceField(
        required=False,
        choices=[("recientes", "Más recientes primero"), ("antiguas", "Más antiguas primero")],
    )
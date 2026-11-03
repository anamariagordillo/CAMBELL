from django import forms

from pagos.models import MetodoPago
from usuarios.localidades import LOCALIDADES, barrios_de

from .models import CategoriaServicio, Solicitud

PRECIO_MINIMO = 15000


class SolicitudForm(forms.ModelForm):
    categoria = forms.ChoiceField(
        label="Categoría del servicio",
        choices=[("", "Selecciona una categoría")] + list(CategoriaServicio.choices),
    )
    metodo_pago = forms.ModelChoiceField(
        queryset=MetodoPago.objects.none(), required=False, label="Método de pago"
    )

    class Meta:
        model = Solicitud
        fields = [
            "descripcion", "categoria", "localidad", "barrio", "latitud", "longitud",
            "direccion_especifica", "precio_ofertado", "metodo_pago",
        ]
        labels = {
            "descripcion": "Descripción del trabajo",
            "localidad": "Localidad",
            "barrio": "Barrio",
            "latitud": "Ubicación en el mapa",
            "longitud": "Ubicación en el mapa",
            "direccion_especifica": "Dirección específica",
            "precio_ofertado": "Precio que ofertas",
        }
        widgets = {
            "descripcion": forms.Textarea(attrs={
                "rows": 3, "placeholder": "Ej. Necesito arreglar una fuga en la cocina...",
            }),
            # Estos cuatro los llena el JavaScript del mapa; la persona no los escribe.
            "localidad": forms.HiddenInput(attrs={"id": "inputLocalidad"}),
            "barrio": forms.HiddenInput(attrs={"id": "inputBarrio"}),
            "latitud": forms.HiddenInput(attrs={"id": "inputLatitud"}),
            "longitud": forms.HiddenInput(attrs={"id": "inputLongitud"}),
            "direccion_especifica": forms.TextInput(attrs={
                "placeholder": "Ej. Cra 15 # 45-32, Apto 301, Torre B",
            }),
            "precio_ofertado": forms.NumberInput(attrs={
                "min": PRECIO_MINIMO, "step": "0.01", "placeholder": "Ej. 150000",
            }),
        }

    def __init__(self, *args, cliente=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo se pueden elegir los métodos de pago del propio cliente.
        if cliente is not None:
            self.fields["metodo_pago"].queryset = MetodoPago.objects.filter(cliente=cliente)

    def clean_precio_ofertado(self):
        precio = self.cleaned_data.get("precio_ofertado")
        if precio is not None and precio < PRECIO_MINIMO:
            raise forms.ValidationError("El precio mínimo es $15.000.")
        return precio

    def clean(self):
        datos = super().clean()
        localidad = datos.get("localidad")
        barrio = datos.get("barrio")

        if not localidad:
            self.add_error("localidad", "Selecciona la localidad.")
        elif localidad not in LOCALIDADES:
            self.add_error("localidad", "La localidad no es válida.")
        elif not barrio:
            self.add_error("barrio", "Selecciona el barrio.")
        elif barrio not in barrios_de(localidad):
            self.add_error("barrio", "El barrio no pertenece a esa localidad.")

        if datos.get("latitud") is None or datos.get("longitud") is None:
            self.add_error("latitud", "Marca el punto de ubicación en el mapa.")
        return datos
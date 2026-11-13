"""Politica de contrasenas de Cambell.

Es la misma regla de la version Java (PasswordPolicyDaoAuthenticationProvider):
entre 8 y 64 caracteres, con al menos una minuscula, una mayuscula y un numero.
Se deja en un solo archivo para que el registro, el cambio y la recuperacion
usen exactamente la misma regla.
"""
import re

# El patron se usa tanto en Python (re.match) como en los formularios de Django.
PATRON_PASSWORD = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,64}$"
_PATRON_COMPILADO = re.compile(PATRON_PASSWORD)

MSG_PASSWORD = (
    "La contraseña debe tener entre 8 y 64 caracteres, "
    "con al menos una mayúscula, una minúscula y un número."
)


def cumple_politica(password):
    """Devuelve True si la contrasena cumple la politica vigente."""
    return bool(password and _PATRON_COMPILADO.match(password))

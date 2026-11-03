"""Catalogo de localidades y barrios de Bogota con coordenadas aproximadas.

Se usa en el registro, en los filtros multicriterio y en el mapa.
Estructura: {localidad: [(barrio, latitud, longitud), ...]}
"""

LOCALIDADES = {
    "Chapinero": [
        ("Chapinero Alto", 4.6533, -74.0513),
        ("Chapinero Central", 4.6482, -74.0636),
        ("El Refugio", 4.6667, -74.0536),
        ("Marly", 4.6455, -74.0594),
        ("San Isidro Patios", 4.6481, -74.0447),
    ],
    "Suba": [
        ("Suba Centro", 4.7485, -74.0831),
        ("El Rincón", 4.7627, -74.1009),
        ("Niza", 4.7210, -74.0800),
        ("La Alhambra", 4.7300, -74.0656),
        ("San José de Bavaria", 4.6950, -74.0722),
    ],
    "Engativá": [
        ("Engativá Pueblo", 4.7075, -74.0967),
        ("Villa Country", 4.6894, -74.0867),
        ("Las Ferias", 4.6928, -74.0969),
        ("El Dorado", 4.7013, -74.1039),
        ("Minuto de Dios", 4.7203, -74.1039),
    ],
    "Kennedy": [
        ("Kennedy Central", 4.6333, -74.1525),
        ("Bosa", 4.6172, -74.1817),
        ("Tintal", 4.6440, -74.1660),
        ("Alamos", 4.6577, -74.1625),
        ("Carvajal", 4.6278, -74.1567),
    ],
    "Usaquén": [
        ("Usaquén Centro", 4.6986, -74.0328),
        ("Santa Bárbara", 4.6970, -74.0450),
        ("Cedritos", 4.7160, -74.0330),
        ("La Carolina", 4.6889, -74.0456),
        ("Santa Ana", 4.7075, -74.0417),
    ],
    "Fontibón": [
        ("Fontibón Pueblo", 4.6719, -74.1442),
        ("Modelia", 4.6728, -74.1197),
        ("El Tintal", 4.6440, -74.1660),
        ("Villemar", 4.6869, -74.1256),
        ("La Capuchina", 4.6781, -74.1425),
    ],
    "Teusaquillo": [
        ("Galerías", 4.6522, -74.0922),
        ("Campín", 4.6511, -74.0864),
        ("Quinta Paredes", 4.6489, -74.0789),
        ("La Soledad", 4.6233, -74.0786),
        ("Palermo", 4.6408, -74.0686),
    ],
    "Puente Aranda": [
        ("Muzú", 4.6289, -74.1239),
        ("San Rafael", 4.6233, -74.1139),
        ("Ciudad Montes", 4.6167, -74.1189),
        ("Veraguas", 4.6331, -74.1169),
        ("Pensilvania", 4.6422, -74.1275),
    ],
    "Barrios Unidos": [
        ("Doce de Octubre", 4.6744, -74.0781),
        ("La Paz", 4.6781, -74.0861),
        ("Alcázares", 4.6817, -74.0792),
        ("Los Andes", 4.6692, -74.0744),
        ("San Fernando", 4.6722, -74.0892),
    ],
    "Antonio Nariño": [
        ("Restrepo", 4.6058, -74.1011),
        ("Ciudad Jardín", 4.6089, -74.1017),
        ("Santander", 4.6189, -74.1097),
        ("San Antonio", 4.5847, -74.1014),
        ("La Fraguita", 4.6111, -74.0967),
    ],
    "Santa Fe": [
        ("La Candelaria", 4.6019, -74.0717),
        ("Las Aguas", 4.6083, -74.0706),
        ("Santa Fe", 4.6050, -74.0792),
        ("Los Mártires", 4.6067, -74.0833),
        ("La Macarena", 4.6125, -74.0756),
    ],
    "Los Mártires": [
        ("La Estanzuela", 4.6058, -74.0989),
        ("La Pepita", 4.6086, -74.0936),
        ("Voto Nacional", 4.6133, -74.0889),
        ("Paloquemao", 4.6186, -74.0947),
        ("La Sabana", 4.6106, -74.0847),
    ],
}


def nombres_localidades():
    return list(LOCALIDADES.keys())


def barrios_de(localidad):
    return [b for b, _, _ in LOCALIDADES.get(localidad, [])]


def localidades_para_mapa():
    """Lista [{localidad, barrios: [{nombre, lat, lon}]}] para los selectores y el mapa."""
    return [
        {
            "localidad": localidad,
            "barrios": [{"nombre": n, "lat": lat, "lon": lon} for n, lat, lon in barrios],
        }
        for localidad, barrios in LOCALIDADES.items()
    ]
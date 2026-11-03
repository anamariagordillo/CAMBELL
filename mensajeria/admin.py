from django.contrib import admin

from .models import DispositivoNotificacion, Mensaje, Notificacion

admin.site.register(Mensaje)
admin.site.register(Notificacion)
admin.site.register(DispositivoNotificacion)

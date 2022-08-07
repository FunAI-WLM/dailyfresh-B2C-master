# -*-coding:utf-8-*-
from django.contrib import admin
from apps.user.models import User, Address

# Register your models here.

admin.site.register(User)

# for model in Address():
#     print("00000  model.__name__ {} ".format(str(model.__name__)))
    # if model._meta.abstract:
    #     raise ImproperlyConfigured(
    #         'The model %s is abstract, so it cannot be registered with admin.' % model.__name__
    #     )

    # if model in self._registry:
    #     registered_admin = str(self._registry[model])

admin.site.register(Address)

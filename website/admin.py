from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from website.models import Profile, LocalityName, GeoReference


# Define an inline admin descriptor for Employee model which acts a bit like a singleton
class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'profile'


# Define a new User admin
class UserAdmin(BaseUserAdmin):
    inlines = (ProfileInline, )

# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

# I want to be able to edit profiles standalone
admin.site.register(Profile, admin.ModelAdmin)
admin.site.register(LocalityName, admin.ModelAdmin)
admin.site.register(GeoReference, admin.ModelAdmin)

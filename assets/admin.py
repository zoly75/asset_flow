from django.contrib import admin
from .models import Asset, UserProfile

# Optional: Customize how the list looks in Admin
class AssetAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'assigned_to', 'owner', 'created_at')
    list_filter = ('status', 'owner')
    search_fields = ('name', 'serial_number', 'assigned_to')

admin.site.register(Asset, AssetAdmin)
admin.site.register(UserProfile)
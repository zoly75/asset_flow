from django.contrib import admin
from .models import Asset, UserProfile, AssetHistory, Employee

# 1. Asset Admin Configuration
class AssetAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'assigned_to', 'owner', 'created_at')
    list_filter = ('status', 'owner')
    # Use double underscore to search inside the related Employee's name
    search_fields = ('name', 'serial_number', 'assigned_to__name')

# 2. Asset History Admin (Read-only log view)
class AssetHistoryAdmin(admin.ModelAdmin):
    list_display = ('date', 'asset', 'action', 'changed_by')
    list_filter = ('date',)
    search_fields = ('asset__name', 'action')
    # Optional: Make fields read-only so history cannot be faked manually
    readonly_fields = ('date', 'asset', 'action', 'changed_by')

# 3. Employee Admin Configuration
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'owner')
    list_filter = ('owner',)
    search_fields = ('name', 'email')

# Registering models
admin.site.register(Asset, AssetAdmin)
admin.site.register(UserProfile)
admin.site.register(AssetHistory, AssetHistoryAdmin)
admin.site.register(Employee, EmployeeAdmin)
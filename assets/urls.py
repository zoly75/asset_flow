from django.urls import path
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from . import views
from .views import SignUpView, CustomPasswordChangeView

urlpatterns = [
    # The root URL of the app triggers the dashboard
    path('', views.dashboard, name='dashboard'),
    path('add/', views.add_asset, name='add_asset'),
    # Example URL: /asset/a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11/
    path('asset/<uuid:uuid>/', views.public_asset, name='public_asset'),
    # Example: /asset/uuid/qr/ -> Returns an image
    path('asset/<uuid:uuid>/qr/', views.generate_qr, name='generate_qr'),

    path('asset/<uuid:uuid>/edit/', views.edit_asset, name='edit_asset'),
    path('asset/<uuid:uuid>/delete/', views.delete_asset, name='delete_asset'),
    path('asset/<uuid:uuid>/assign/', views.assign_asset, name='assign_asset'),
    path('asset/<uuid:uuid>/return/', views.return_asset, name='return_asset'),
    path('asset/<uuid:uuid>/status/', views.update_status, name='update_status'),
    path('labels/pdf/', views.download_labels_pdf, name='download_labels'),
    path('settings/', views.profile_settings, name='profile_settings'),
    path('accounts/password_change/', CustomPasswordChangeView.as_view(), name='password_change'),
    path('employees/', views.employee_list, name='employee_list'),
    path('employees/delete/<int:pk>/', views.delete_employee, name='delete_employee'),
    path('employees/edit/<int:pk>/', views.edit_employee, name='edit_employee'),
    path('signup/', SignUpView.as_view(), name='signup'),
    path('pricing/', views.pricing, name='pricing'),
    path('team/', views.team_list, name='team_list'),
    path('team/add/', views.add_team_member, name='add_team_member'),
    path('team/delete/<int:pk>/', views.delete_team_member, name='delete_team_member'),
    path('help/', views.help_page, name='help'),
]
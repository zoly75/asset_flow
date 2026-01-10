from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils.safestring import mark_safe
from .models import Asset, UserProfile, Employee

class BaseAssetForm(forms.ModelForm):
    """
    Base form that handles the 'assigned_to' field logic.
    Other forms will inherit from this to avoid repetition.
    """
    assigned_to = forms.ModelChoiceField(
        queryset=Employee.objects.none(), # Empty default
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Assign to Employee",
        empty_label="-- Not Assigned --"
    )

    def __init__(self, *args, **kwargs):
        # Extract user safely
        user = kwargs.pop('user', None)
        super(BaseAssetForm, self).__init__(*args, **kwargs)
        
        if user:
            # Centralized filtering logic
            self.fields['assigned_to'].queryset = Employee.objects.filter(owner=user).order_by('name')

class AssetForm(BaseAssetForm):
    """
    Full create/edit form. Inherits assigned_to logic from BaseAssetForm.
    """
    class Meta:
        model = Asset
        fields = ['name', 'description', 'serial_number', 'status', 'assigned_to']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'serial_number': forms.TextInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            # assigned_to is handled by BaseAssetForm
        }

class EmployeeForm(forms.ModelForm):
    """
    Form to add/edit employees (Team members).
    """
    class Meta:
        model = Employee
        fields = ['name', 'email', 'phone']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Optional'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional'}),
        }

class AssignAssetForm(BaseAssetForm):
    """
    Quick assign form (only employee selection).
    """
    class Meta:
        model = Asset
        fields = ['assigned_to']
        # We don't need status here, the model.save() logic will handle it!
        
class AssetStatusForm(BaseAssetForm):
    """
    Quick status update form. Inherits assigned_to logic.
    """
    class Meta:
        model = Asset
        fields = ['status', 'assigned_to']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
        }
    
class UserProfileForm(forms.ModelForm):
    """
    Form for users to edit their company details.
    """
    class Meta:
        model = UserProfile
        fields = ['company_name', 'phone_number', ]
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Acme Corp'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. +36 30 123 4567'}),
        }

class UserUpdateForm(forms.ModelForm):
    """
    Form to update standard User data (Email, First Name, Last Name).
    """
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control'}))

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
        }

class SignUpForm(UserCreationForm):
    """
    Custom registration form that includes EMAIL.
    """
    email = forms.EmailField(required=True, help_text="Required. Used for password reset.")
    first_name = forms.CharField(max_length=30, required=False)
    last_name = forms.CharField(max_length=30, required=False)

    # Checkbox that MUST be checked to proceed.
    # We use mark_safe to allow HTML links inside the label.
    terms_confirmed = forms.BooleanField(
        required=True,
        label=mark_safe(
            'I have read and agree to the '
            '<a href="/terms/" target="_blank">Terms of Service</a> and '
            '<a href="/privacy/" target="_blank">Privacy Policy</a>.'
        )
    )
    class Meta:
        model = User
        # Itt határozzuk meg, mi jelenjen meg.
        # A jelszót a UserCreationForm automatikusan hozzáadja.
        fields = ('username', 'email', 'first_name', 'last_name')

    def clean_email(self):
        email = self.cleaned_data.get('email')
        
        # 1. Check if an ACTIVE user already exists with this email
        if User.objects.filter(email=email, is_active=True).exists():
            raise forms.ValidationError("This email address is already in use by an active account.")
        
        # 2. Check for INACTIVE users (stalled registrations)
        # If someone registered but never activated, we delete the old "ghost" user
        # so they can try registering again immediately.
        inactive_users = User.objects.filter(email=email, is_active=False)
        if inactive_users.exists():
            inactive_users.delete()
            
        return email

class TeamUserCreationForm(UserCreationForm):
    """
    Form to create a sub-user (Team Member).
    Simplified registration: only Username + Password (auto-generated or set).
    """
    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email')
    
    def __init__(self, *args, **kwargs):
        super(TeamUserCreationForm, self).__init__(*args, **kwargs)
        # Make email optional for team members if they don't want to provide it
        self.fields['email'].required = False
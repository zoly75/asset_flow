from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
import uuid  # <--- Standard library for generating unique IDs

class Employee(models.Model):
    """
    Represents a staff member / employee of the SaaS user's company.
    """
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True, null=True)

    def __str__(self):
        return self.name

class Asset(models.Model):
    """
    Represents a physical asset (Laptop, Drill, Car, etc.).
    """

    # --- 1. SAAS POINTER (Multi-tenancy) ---
    # Links this asset to a specific user account (Tenant).
    # Essential for ensuring users only see their own assets.
    owner = models.ForeignKey(User, on_delete=models.CASCADE)

    # --- 2. PUBLIC IDENTIFIER (Security) ---
    # We use UUID (e.g., 'a0eebc99-9c0b-4ef8...') for public URLs and QR codes.
    # Why? So competitors can't guess asset count by incrementing IDs (/asset/5, /asset/6).
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # --- 3. CORE DATA ---
    name = models.CharField(max_length=100)  # e.g., "MacBook Pro M1"
    description = models.TextField(blank=True, null=True)
    serial_number = models.CharField(max_length=100, blank=True, null=True)

    # --- 4. STATUS ENUM ---
    # Like a C enum, restricting values to a specific set.
    STATUS_AVAILABLE = 'AVAILABLE'
    STATUS_ASSIGNED = 'ASSIGNED'
    STATUS_MAINTENANCE = 'MAINTENANCE'
    STATUS_LOST = 'LOST'
    STATUS_BROKEN = 'BROKEN'

    STATUS_CHOICES = [
        (STATUS_AVAILABLE, 'Available'),     # Stored Value, Display Value
        (STATUS_ASSIGNED, 'Assigned / In Use'),
        (STATUS_MAINTENANCE, 'In Maintenance'),
        (STATUS_LOST, 'Lost / Stolen'),
        (STATUS_BROKEN, 'Broken / Decommissioned'),
    ]
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_AVAILABLE
    )

    # --- 5. ASSIGNMENT ---
    assigned_to = models.ForeignKey(
        Employee, 
        on_delete=models.SET_NULL, # If employee is deleted, asset becomes 'unassigned' (not deleted)
        null=True, 
        blank=True,
        related_name='assets' # Allows retrieving assets via employee.assets.all()
    )

    # --- 6. TIMESTAMPS ---
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        """
        Override save method to centralize business logic.
        Ensures consistency between status and assigned_to fields.
        """
        
        # 1. If assigned to someone, force status to ASSIGNED (unless it is broken/maintenance/lost)
        # We check if status is AVAILABLE to avoid overwriting specific states like BROKEN.
        if self.assigned_to and self.status == self.STATUS_AVAILABLE:
            self.status = self.STATUS_ASSIGNED
            
        # 2. If status is explicitly set to AVAILABLE, remove the employee
        if self.status == self.STATUS_AVAILABLE:
            self.assigned_to = None

        # 3. If user unassigned the employee (set to None) but left status as ASSIGNED,
        # we should revert status to AVAILABLE.
        if self.assigned_to is None and self.status == self.STATUS_ASSIGNED:
            self.status = self.STATUS_AVAILABLE

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.status})"

class UserProfile(models.Model):
    """
    Extension of the User model to store company details.
    One User = One Company Profile.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    company_name = models.CharField(max_length=100, blank=True, default="")
    phone_number = models.CharField(max_length=30, blank=True, default="")

    is_premium = models.BooleanField(default=False) 
    max_assets = models.IntegerField(default=50)

    def __str__(self):
        return f"{self.company_name} ({self.user.username})"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Automatic trigger:
    When a User is created (Sign Up), automatically create a UserProfile for them.
    """
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """
    Ensures the profile is saved when the user is saved.
    """
    try:
        instance.userprofile.save()
    except UserProfile.DoesNotExist:
        UserProfile.objects.create(user=instance)
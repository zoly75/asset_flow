# assets/signals.py
from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import Asset, AssetHistory

@receiver(pre_save, sender=Asset)
def track_asset_changes(sender, instance, **kwargs):
    """
    Signal receiver that runs BEFORE an Asset is saved.
    It compares the incoming instance with the one already in the DB.
    """
    # Only check existing assets (not new creations)
    if instance.pk: 
        try:
            # Fetch the old version from the database
            old_asset = Asset.objects.get(pk=instance.pk)
            
            changes = []
            
            # 1. Check for Status Change
            if old_asset.status != instance.status:
                old_status_label = dict(Asset.STATUS_CHOICES).get(old_asset.status, old_asset.status)
                new_status_label = dict(Asset.STATUS_CHOICES).get(instance.status, instance.status)
                changes.append(f"Status: {old_status_label} -> {new_status_label}")
                
            # 2. Check for Assignment Change
            if old_asset.assigned_to != instance.assigned_to:
                old_name = old_asset.assigned_to.name if old_asset.assigned_to else "Storage"
                new_name = instance.assigned_to.name if instance.assigned_to else "Storage"
                changes.append(f"Assigned to: {old_name} -> {new_name}")

            # If there are any changes, create a history record
            if changes:
                action_text = ", ".join(changes)
                
                # Note: signals don't have direct access to 'request.user'.
                # As a fallback, we use the asset owner, OR we can handle user tracking
                # in the View logic. For now, we log the owner as the changer to keep it simple.
                AssetHistory.objects.create(
                    asset=instance,
                    action=action_text,
                    changed_by=instance.owner 
                )
                
        except Asset.DoesNotExist:
            pass # Should not happen, but safe to ignore
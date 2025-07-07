# GRPR/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Scorecard, Forty        # local imports
# Games comes along via instance.GameID, no circular-import risk

@receiver(post_save, sender=Scorecard)
@receiver(post_save, sender=Forty)
def maybe_lock_game(sender, instance, **kwargs):
    game = instance.GameID
    if not game.IsLocked and game.is_complete:
        game.IsLocked = True
        game.LockedAt = timezone.now()
        game.save(update_fields=["IsLocked", "LockedAt"])

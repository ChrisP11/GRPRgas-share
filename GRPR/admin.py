from django.contrib import admin
from django.utils import timezone
from .models import UserProfile, Games

admin.site.register(UserProfile)

@admin.action(description="Lock selected games")
def lock_games(modeladmin, request, queryset):
    queryset.update(IsLocked=True, LockedAt=timezone.now())

@admin.action(description="Unlock selected games")
def unlock_games(modeladmin, request, queryset):
    queryset.update(IsLocked=False, LockedAt=None)

@admin.register(Games)
class GamesAdmin(admin.ModelAdmin):
    list_display = ("id", "PlayDate", "Status", "IsLocked")
    actions = [lock_games, unlock_games]
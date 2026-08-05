from django.contrib import admin

from .models import Card, Deck, DeckCard, Game, GamePlayer, MoveLog, Profile, Round


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "games_played", "games_won", "total_score", "updated_at")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")


class GamePlayerInline(admin.TabularInline):
    model = GamePlayer
    extra = 0
    readonly_fields = ("joined_at",)


class RoundInline(admin.TabularInline):
    model = Round
    extra = 0
    readonly_fields = ("created_at", "resolved_at")


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "status",
        "current_round",
        "winner",
        "created_at",
        "started_at",
        "finished_at",
    )
    list_filter = ("status", "created_at", "started_at", "finished_at")
    readonly_fields = ("created_at", "started_at", "finished_at", "stats_recorded_at")
    inlines = (GamePlayerInline, RoundInline)


@admin.register(GamePlayer)
class GamePlayerAdmin(admin.ModelAdmin):
    list_display = ("id", "game", "user", "position", "score", "joined_at")
    list_filter = ("position",)
    search_fields = ("user__username", "game__id")
    readonly_fields = ("joined_at",)


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ("id", "suit", "rank")
    list_filter = ("suit", "rank")
    search_fields = ("suit", "rank")


@admin.register(Deck)
class DeckAdmin(admin.ModelAdmin):
    list_display = ("id", "game", "created_at", "shuffled_at")
    readonly_fields = ("created_at", "shuffled_at")


@admin.register(DeckCard)
class DeckCardAdmin(admin.ModelAdmin):
    list_display = ("id", "deck", "card", "owner", "position", "is_played", "played_at")
    list_filter = ("is_played", "card__suit", "card__rank")
    search_fields = ("owner__user__username", "deck__game__id")
    readonly_fields = ("played_at",)


@admin.register(Round)
class RoundAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "game",
        "number",
        "player_one_card",
        "player_two_card",
        "winner",
        "is_resolved",
    )
    list_filter = ("is_resolved", "number")
    search_fields = ("game__id",)
    readonly_fields = ("created_at", "resolved_at")


@admin.register(MoveLog)
class MoveLogAdmin(admin.ModelAdmin):
    list_display = ("id", "game", "round", "player", "action", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("game__id", "player__user__username")
    readonly_fields = ("game", "round", "player", "action", "details", "created_at")

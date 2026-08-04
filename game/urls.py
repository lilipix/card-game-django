from django.urls import path

from . import views

app_name = "game"

urlpatterns = [
    path(
        "",
        views.game_list,
        name="game_list",
    ),
    path(
        "mine/",
        views.my_games,
        name="my_games",
    ),
    path(
        "create/",
        views.game_create,
        name="game_create",
    ),
    path(
        "<int:game_id>/",
        views.game_detail,
        name="game_detail",
    ),
    path(
        "<int:game_id>/state/",
        views.game_state,
        name="game_state",
    ),
    path(
        "<int:game_id>/rounds/",
        views.game_rounds,
        name="game_rounds",
    ),
    path(
        "<int:game_id>/cards/",
        views.player_cards,
        name="player_cards",
    ),
    path(
        "<int:game_id>/join/",
        views.game_join,
        name="game_join",
    ),
    path(
        "<int:game_id>/play/",
        views.play_card_view,
        name="play_card",
    ),
]

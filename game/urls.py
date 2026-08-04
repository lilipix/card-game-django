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
        "<int:game_id>/join/",
        views.game_join,
        name="game_join",
    ),
]

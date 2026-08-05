from django.urls import path

from . import views

app_name = "game"

urlpatterns = [
    path("", views.home, name="home"),
    path("games/", views.game_list, name="list"),
    path("games/create/", views.create_game, name="create"),
    path("games/<int:pk>/join/", views.join_game, name="join"),
    path("games/<int:pk>/waiting-room/", views.waiting_room, name="waiting_room"),
    path("games/<int:pk>/start/", views.start_game, name="start"),
    path("games/<int:pk>/board/", views.game_board, name="board"),
    path("games/<int:pk>/play/", views.play_card, name="play_card"),
    path("games/<int:pk>/result/", views.game_result, name="result"),
    path("games/<int:game_id>/", views.game_detail, name="game_detail"),
    path("signup/", views.SignUpView.as_view(), name="signup"),
]

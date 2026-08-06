from django.urls import path

from . import views

app_name = "game"

urlpatterns = [
    path("home/", views.home, name="home"),
    # Liste des parties en attente accessibles au joueur connecté.
    path(
        "",
        views.game_list,
        name="game_list",
    ),
    # Création d'une nouvelle partie. Route appelée uniquement en POST.
    path(
        "create/",
        views.game_create,
        name="game_create",
    ),
    # Liste JSON des parties du joueur connecté.
    path(
        "mine/",
        views.my_games,
        name="my_games",
    ),
    # Affichage HTML de la salle d'attente ou du plateau de jeu.
    path(
        "<int:game_id>/",
        views.game_detail,
        name="game_detail",
    ),
    # Inscription comme joueur 2 puis démarrage de la partie. Route POST.
    path(
        "<int:game_id>/join/",
        views.game_join,
        name="game_join",
    ),
    # Intention d'ajouter une carte pour le joueur connecté. Route POST.
    path(
        "<int:game_id>/play-card/",
        views.game_play_card,
        name="game_play_card",
    ),
    # Etat JSON sérialisé selon l'utilisateur connecté, prévu pour le polling GET.
    path(
        "<int:game_id>/state/",
        views.game_state,
        name="game_state",
    ),
    path(
        "<int:game_id>/result/",
        views.game_result,
        name="game_result",
    ),
    path("signup/", views.SignUpView.as_view(), name="signup"),
]

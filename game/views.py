from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .game_engine import GameRuleError, create_game, join_game, play_card, start_game
from .models import Game, GamePlayer
from .serializers import serialize_game_for_user


@login_required
def game_list(request: HttpRequest) -> HttpResponse:
    """Affiche les parties en attente qui peuvent être rejointes."""

    available_games = (
        Game.objects.filter(status=Game.Status.WAITING)
        # Compte les participants de chaque partie.
        .annotate(players_count=Count("players"))
        # Une partie disponible doit contenir uniquement son créateur.
        .filter(players_count=1)
        # L'utilisateur ne doit pas déjà participer à la partie.
        .exclude(players__user=request.user)
        .order_by("-created_at")
    )

    return render(
        request,
        "game/game_list.html",
        {"available_games": available_games},
    )


@login_required
@require_POST
def game_create(request: HttpRequest) -> HttpResponse:
    """Crée une partie avec l'utilisateur connecté comme joueur 1."""

    try:
        game = create_game(request.user)
    except GameRuleError as error:
        messages.error(request, str(error))
        return redirect("game:game_list")

    messages.success(
        request,
        "La partie a été créée. En attente d'un adversaire.",
    )

    return redirect("game:game_detail", game_id=game.pk)


@login_required
def game_detail(
    request: HttpRequest,
    game_id: int,
) -> HttpResponse:
    """Affiche la salle d'attente ou le plateau de jeu."""

    game = get_object_or_404(
        Game.objects.select_related("winner"),
        pk=game_id,
    )

    # Empêche une personne extérieure de consulter une partie.
    if not GamePlayer.objects.filter(
        game=game,
        user=request.user,
    ).exists():
        return HttpResponseForbidden("Vous ne participez pas à cette partie.")

    players = (
        GamePlayer.objects.filter(
            game=game,
        )
        .select_related("user")
        .order_by("position")
    )

    context = {
        "game": game,
        "players": players,
        # Etat initial déjà filtré selon le joueur connecté avant rendu HTML.
        "game_state": serialize_game_for_user(game, request.user),
    }

    # Tant que le deuxième joueur n'est pas arrivé,
    # le créateur voit la salle d'attente.
    if game.status == Game.Status.WAITING:
        return render(
            request,
            "game/waiting_room.html",
            context,
        )

    # Une fois la partie démarrée, on affiche le plateau.
    return render(
        request,
        "game/game_board.html",
        context,
    )


@login_required
@require_POST
def game_join(
    request: HttpRequest,
    game_id: int,
) -> HttpResponse:
    """Ajoute l'utilisateur comme joueur 2 et démarre la partie."""

    game = get_object_or_404(Game, pk=game_id)

    try:
        # Si le démarrage échoue, l'inscription du joueur 2
        # est également annulée grâce à la transaction globale.
        with transaction.atomic():
            join_game(game, request.user)
            started_game = start_game(game)

    except GameRuleError as error:
        messages.error(request, str(error))
        return redirect("game:game_list")

    messages.success(request, "La partie commence !")

    return redirect(
        "game:game_detail",
        game_id=started_game.pk,
    )


@login_required
@require_POST
def game_play_card(
    request: HttpRequest,
    game_id: int,
) -> JsonResponse:
    """Reçoit uniquement l'intention du joueur d'ajouter une carte."""

    game = get_object_or_404(Game, pk=game_id)

    try:
        # Le client n'envoie aucune carte: seul le moteur décide quoi jouer.
        play_card(game, request.user)
    except GameRuleError as error:
        return JsonResponse({"error": str(error)}, status=error.status_code)

    game.refresh_from_db()
    return JsonResponse(serialize_game_for_user(game, request.user))


@login_required
@require_GET
def game_state(
    request: HttpRequest,
    game_id: int,
) -> JsonResponse:
    """Renvoie l'état sérialisé de la partie visible par le joueur connecté."""

    game = get_object_or_404(Game, pk=game_id)

    # Le polling expose le même état filtré que le rendu HTML et les réponses POST.
    if not GamePlayer.objects.filter(game=game, user=request.user).exists():
        return JsonResponse(
            {"error": "Vous ne participez pas à cette partie."},
            status=403,
        )

    return JsonResponse(serialize_game_for_user(game, request.user))

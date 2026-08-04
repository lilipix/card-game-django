from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .game_engine import create_game, join_game, play_card, start_game
from .models import Game, GamePlayer


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
    except ValueError as error:
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

    except ValueError as error:
        messages.error(request, str(error))
        return redirect("game:game_list")

    messages.success(request, "La partie commence !")

    return redirect(
        "game:game_detail",
        game_id=started_game.pk,
    )


@login_required
@require_POST
def play_card_view(request, game_id):
    """Permet au joueur connecté de jouer sa prochaine carte."""

    game = get_object_or_404(Game, pk=game_id)

    player = get_object_or_404(
        GamePlayer,
        game=game,
        user=request.user,
    )

    try:
        card = play_card(game, player)
    except ValueError as error:
        return JsonResponse(
            {"error": str(error)},
            status=400,
        )

    game.refresh_from_db()

    return JsonResponse(
        {
            "card": {
                "id": card.pk,
                "rank": card.get_rank_display(),  # type: ignore[reportAttributeAccessIssue]
                "suit": card.get_suit_display(),  # type: ignore[reportAttributeAccessIssue]
            },
            "game": {
                "status": game.status,
                "current_round": game.current_round,
            },
        }
    )

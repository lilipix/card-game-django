from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import CreateView

from .game_engine import GameRuleError, create_game, join_game, play_card, start_game
from .models import Game, GamePlayer
from .serializers import serialize_game_for_user


class SignUpView(CreateView):
    form_class = UserCreationForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("game:game_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response


def home(request: HttpRequest) -> HttpResponse:
    return render(request, "game/home.html")


@login_required
def game_list(request: HttpRequest) -> HttpResponse:
    """Affiche les parties en attente qui peuvent être rejointes."""

    # On affiche uniquement les parties en attente avec une place disponible,
    # et on retire celles auxquelles l'utilisateur participe déjà.
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

    user_games = (
        Game.objects.filter(players__user=request.user)
        .annotate(players_count=Count("players"))
        .distinct()
        .order_by("-created_at")
    )

    return render(
        request,
        "game/game_list.html",
        {
            "available_games": available_games,
            "user_games": user_games,
        },
    )


@login_required
def my_games(request: HttpRequest) -> JsonResponse:
    """Liste les parties auxquelles participe l'utilisateur connecté."""

    games = (
        Game.objects.filter(players__user=request.user)
        .select_related("winner")
        .distinct()
        .order_by("-created_at")
    )

    # Chaque partie est sérialisée avec les mêmes règles de visibilité que le plateau.
    return JsonResponse(
        {
            "games": [serialize_game_for_user(game, request.user) for game in games],
        }
    )


@login_required
@require_POST
def game_create(request: HttpRequest) -> HttpResponse:
    """Crée une partie avec l'utilisateur connecté comme joueur 1."""

    # Le moteur contient les règles métier ; la vue se limite à gérer
    # la requête HTTP, les messages utilisateur et la redirection.
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

    # On charge le gagnant avec la partie pour éviter une requête
    # supplémentaire si la partie est terminée.
    game = get_object_or_404(
        Game.objects.select_related(
            "winner",
            "winner__user",
        ),
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

    player_one = next((p for p in players if p.position == GamePlayer.Position.PLAYER_ONE), None)
    player_two = next((p for p in players if p.position == GamePlayer.Position.PLAYER_TWO), None)
    is_player_one = bool(player_one and player_one.user_id == request.user.id)
    current_player = next((p for p in players if p.user_id == request.user.id), None)
    opponent = next((p for p in players if p.user_id != request.user.id), None)

    if current_player is None:
        return HttpResponseForbidden("Vous ne participez pas à cette partie.")

    context = {
        "game": game,
        "players": players,
        "player_one": player_one,
        "player_two": player_two,
        "is_player_one": is_player_one,
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

    if game.status == Game.Status.FINISHED:
        return redirect("game:game_result", game_id=game.pk)

    current_round = game.rounds.filter(number=game.current_round).first()
    if current_round is None:
        messages.error(request, "La manche en cours est introuvable.")
        return render(request, "game/game_board.html", context)

    my_card = current_round.card_for(current_player)
    opponent_card = current_round.card_for(opponent) if opponent is not None else None
    player_one_has_card = current_round.player_one_card_id is not None
    player_two_has_card = current_round.player_two_card_id is not None
    expected_position = (
        GamePlayer.Position.PLAYER_TWO
        if player_one_has_card
        else GamePlayer.Position.PLAYER_ONE
    )
    can_play = (
        not current_round.is_resolved
        and my_card is None
        and current_player.position == expected_position
    )

    last_round = game.rounds.filter(is_resolved=True).order_by("-number").first()
    context.update(
        {
            "current_round": current_round,
            "current_player": current_player,
            "opponent": opponent,
            "can_play": can_play,
            "waiting_for_opponent": my_card is not None and not current_round.is_resolved,
            "displayed_player_card": my_card,
            "displayed_opponent_card": opponent_card if current_round.is_resolved else None,
            "last_round": last_round,
        }
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
) -> HttpResponse:
    """Reçoit uniquement l'intention du joueur d'ajouter une carte."""

    game = get_object_or_404(Game, pk=game_id)

    try:
        # Le client n'envoie aucune carte: seul le moteur décide quoi jouer.
        play_card(game, request.user)
    except GameRuleError as error:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"error": str(error)}, status=error.status_code)
        messages.error(request, str(error))
        return redirect("game:game_detail", game_id=game.pk)

    game.refresh_from_db()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse(serialize_game_for_user(game, request.user))
    return redirect("game:game_detail", game_id=game.pk)


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


@login_required
def game_result(
    request: HttpRequest,
    game_id: int,
) -> HttpResponse:
    game = get_object_or_404(
        Game.objects.select_related("winner", "winner__user"),
        pk=game_id,
        status=Game.Status.FINISHED,
    )

    current_player = get_object_or_404(GamePlayer.objects.select_related("user"), game=game, user=request.user)
    opponent = (
        GamePlayer.objects.select_related("user")
        .filter(game=game)
        .exclude(user=request.user)
        .first()
    )

    if game.winner_id is None:
        outcome = "draw"
    elif game.winner_id == current_player.id:
        outcome = "win"
    else:
        outcome = "loss"

    return render(
        request,
        "game/game_result.html",
        {
            "game": game,
            "current_player": current_player,
            "opponent": opponent,
            "outcome": outcome,
        },
    )

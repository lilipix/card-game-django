from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .game_engine import create_game, join_game, play_card, start_game
from .models import Game, GameCard, GamePlayer, Round


# Les fonctions serialize_* transforment les objets Django en dictionnaires.
# Elles évitent de répéter la même structure JSON dans chaque vue.
def serialize_card(card: GameCard | None) -> dict | None:
    """Retourne une carte sous une forme exploitable en JSON."""

    # Une carte peut être absente lorsqu'un joueur n'a pas encore joué.
    if card is None:
        return None

    return {
        "id": card.pk,
        "rank": card.get_rank_display(),  # type: ignore[attr-defined]
        "suit": card.get_suit_display(),  # type: ignore[attr-defined]
        "position": card.position,
        "is_played": card.is_played,
    }


def serialize_player(player: GamePlayer) -> dict:
    """Retourne les informations publiques d'un participant."""

    # On n'expose volontairement que les champs utiles au jeu.
    return {
        "id": player.pk,
        "username": player.user.username,
        "position": player.position,
        "position_label": player.get_position_display(),  # type: ignore[attr-defined]
        "score": player.score,
    }


def serialize_round(round_: Round) -> dict:
    """Retourne l'état public d'une manche."""

    # Les cartes d'une manche ne sont révélées que lorsque les deux joueurs
    # ont joué. Cela évite qu'un joueur voie la carte adverse trop tôt.
    both_players_have_played = (
        round_.player_one_card is not None
        and round_.player_two_card is not None
    )

    return {
        "id": round_.pk,
        "number": round_.number,
        "player_one_has_played": round_.player_one_card is not None,
        "player_two_has_played": round_.player_two_card is not None,
        "player_one_card": (
            serialize_card(round_.player_one_card)
            if both_players_have_played
            else None
        ),
        "player_two_card": (
            serialize_card(round_.player_two_card)
            if both_players_have_played
            else None
        ),
        "winner": (
            serialize_player(round_.winner)
            if round_.winner is not None
            else None
        ),
        "is_draw": round_.is_draw,
        "is_resolved": round_.is_resolved,
        "resolved_at": round_.resolved_at,
    }

def serialize_game(game: Game) -> dict:
    """Retourne l'état principal d'une partie."""

    # Ce résumé est utilisé par les vues JSON pour afficher l'avancement
    # sans charger tout l'historique des manches.
    return {
        "id": game.pk,
        "status": game.status,
        "status_label": game.get_status_display(),  # type: ignore[attr-defined]
        "current_round": game.current_round,
        "winner": serialize_player(game.winner) if game.winner else None,
        "created_at": game.created_at,
        "started_at": game.started_at,
        "finished_at": game.finished_at,
    }


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

    return render(
        request,
        "game/game_list.html",
        {"available_games": available_games},
    )


@login_required
def my_games(request: HttpRequest) -> JsonResponse:
    """Liste les parties auxquelles participe l'utilisateur connecté."""

    # select_related/prefetch_related limitent le nombre de requêtes SQL
    # au moment de sérialiser les gagnants et les joueurs.
    games = (
        Game.objects.filter(players__user=request.user)
        .select_related("winner", "winner__user")
        .prefetch_related("players", "players__user")
        .distinct()
        .order_by("-created_at")
    )

    return JsonResponse(
        {
            "games": [
                {
                    **serialize_game(game),
                    "players": [
                        serialize_player(player)
                        for player in game.players.all()  # type: ignore[attr-defined]
                    ],
                }
                for game in games
            ],
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
def game_state(
    request: HttpRequest,
    game_id: int,
) -> JsonResponse:
    """Retourne l'état complet d'une partie pour le front."""

    # Cette route sert à rafraîchir le plateau côté front sans recharger
    # toute la page HTML.
    game = get_object_or_404(
        Game.objects.select_related("winner", "winner__user").prefetch_related(
            "players",
            "players__user",
        ),
        pk=game_id,
    )

    # Toutes les routes d'une partie vérifient que l'utilisateur connecté
    # fait bien partie des deux participants.
    if not GamePlayer.objects.filter(game=game, user=request.user).exists():
        return JsonResponse(
            {"error": "Vous ne participez pas à cette partie."},
            status=403,
        )

    current_round = (
        Round.objects.filter(game=game, number=game.current_round)
        .select_related(
            "player_one_card",
            "player_two_card",
            "winner",
            "winner__user",
        )
        .first()
    )

    # La réponse contient la partie, les joueurs et la manche courante :
    # c'est le minimum utile pour reconstruire le plateau.
    return JsonResponse(
        {
            "game": serialize_game(game),
            "players": [
                serialize_player(player)
                for player in game.players.all()  # type: ignore[attr-defined]
            ],
            "current_round": serialize_round(current_round) if current_round else None,
        }
    )


@login_required
def game_rounds(
    request: HttpRequest,
    game_id: int,
) -> JsonResponse:
    """Liste toutes les manches d'une partie."""

    game = get_object_or_404(Game, pk=game_id)

    # L'historique complet reste privé aux deux participants.
    if not GamePlayer.objects.filter(game=game, user=request.user).exists():
        return JsonResponse(
            {"error": "Vous ne participez pas à cette partie."},
            status=403,
        )

    rounds = (
        Round.objects.filter(game=game)
        .select_related(
            "player_one_card",
            "player_two_card",
            "winner",
            "winner__user",
        )
        .order_by("number")
    )

    return JsonResponse({"rounds": [serialize_round(round_) for round_ in rounds]})


@login_required
def player_cards(
    request: HttpRequest,
    game_id: int,
) -> JsonResponse:
    """Liste les cartes du joueur connecté dans une partie."""

    game = get_object_or_404(Game, pk=game_id)
    # get_object_or_404 joue aussi le rôle de contrôle d'accès :
    # aucun autre joueur ne peut demander cette main.
    player = get_object_or_404(GamePlayer, game=game, user=request.user)

    cards = GameCard.objects.filter(game=game, owner=player).order_by("position")

    return JsonResponse(
        {
            "player": serialize_player(player),
            "cards": [serialize_card(card) for card in cards],
        }
    )


@login_required
@require_POST
def play_card_view(
    request: HttpRequest,
    game_id: int,
) -> JsonResponse:
    """Permet au joueur connecté de jouer sa prochaine carte."""

    game = get_object_or_404(Game, pk=game_id)

    # Seul un participant peut jouer une carte dans la partie.
    player = get_object_or_404(
        GamePlayer,
        game=game,
        user=request.user,
    )

    # Mémorise la manche pendant laquelle la carte va être jouée.
    played_round_number = game.current_round

    try:
        # play_card applique toutes les règles : ordre des cartes,
        # résolution automatique de la manche et fin de partie éventuelle.
        card = play_card(game, player)
    except ValueError as error:
        return JsonResponse(
            {"error": str(error)},
            status=400,
        )

    # Recharge la partie, car le moteur peut avoir modifié :
    # - le numéro de la manche ;
    # - le statut ;
    # - le gagnant final.
    game = (
        Game.objects.select_related(
            "winner",
            "winner__user",
        )
        .get(pk=game.pk)
    )

    # Récupère la manche dans laquelle la carte vient réellement d'être jouée.
    played_round = (
        Round.objects.filter(
            game=game,
            number=played_round_number,
        )
        .select_related(
            "player_one_card",
            "player_two_card",
            "winner",
            "winner__user",
        )
        .first()
    )

    return JsonResponse(
        {
            "card": serialize_card(card),
            "game": serialize_game(game),
            "played_round": (
                serialize_round(played_round)
                if played_round
                else None
            ),
        }
    )

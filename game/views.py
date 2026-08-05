from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView

from . import game_engine
from .models import Game, GamePlayer


class SignUpView(CreateView):
    """Inscription : Django gère déjà l'authentification, on ne construit que le formulaire."""

    form_class = UserCreationForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("game:home")

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response


def home(request):
    return render(request, "game/home.html")


@login_required
def game_list(request):
    games = list(
        Game.objects.all().prefetch_related("players__user").order_by("-created_at")
    )
    for game in games:
        game.player_count = game.players.count()
        game.already_joined = any(p.user_id == request.user.id for p in game.players.all())
        game.is_joinable = (
            game.status == Game.Status.WAITING
            and not game.already_joined
            and game.player_count < 2
        )

    return render(request, "game/game_list.html", {"games": games})


@login_required
@require_POST
def create_game(request):
    game = Game.objects.create()
    GamePlayer.objects.create(
        game=game,
        user=request.user,
        position=GamePlayer.Position.PLAYER_ONE,
    )
    return redirect("game:waiting_room", pk=game.pk)


@login_required
@require_POST
def game_create(request):
    return create_game(request)


@login_required
@require_POST
def join_game(request, pk):
    game = get_object_or_404(Game, pk=pk)

    if game.players.filter(user=request.user).exists():
        return redirect("game:waiting_room", pk=game.pk)

    if game.status != Game.Status.WAITING or game.players.count() >= 2:
        messages.error(request, "Cette partie n'est plus disponible.")
        return redirect("game:list")

    GamePlayer.objects.create(
        game=game,
        user=request.user,
        position=GamePlayer.Position.PLAYER_TWO,
    )
    return redirect("game:waiting_room", pk=game.pk)


@login_required
@require_POST
def game_join(request, game_id):
    return join_game(request, game_id)


@login_required
def waiting_room(request, pk):
    game = get_object_or_404(Game, pk=pk, players__user=request.user)

    if game.status == Game.Status.IN_PROGRESS:
        return redirect("game:board", pk=game.pk)
    if game.status == Game.Status.FINISHED:
        return redirect("game:result", pk=game.pk)

    player_one = game.players.filter(position=GamePlayer.Position.PLAYER_ONE).first()
    player_two = game.players.filter(position=GamePlayer.Position.PLAYER_TWO).first()
    is_player_one = bool(player_one and player_one.user_id == request.user.id)

    return render(
        request,
        "game/waiting_room.html",
        {
            "game": game,
            "player_one": player_one,
            "player_two": player_two,
            "is_player_one": is_player_one,
            "can_start": is_player_one and player_two is not None,
        },
    )


@login_required
@require_POST
def start_game(request, pk):
    game = get_object_or_404(Game, pk=pk, players__user=request.user)
    player_one = game.players.filter(position=GamePlayer.Position.PLAYER_ONE).first()

    if game.status != Game.Status.WAITING:
        return redirect("game:board", pk=game.pk)
    if player_one is None or player_one.user_id != request.user.id:
        messages.error(request, "Seul le créateur de la partie peut la lancer.")
        return redirect("game:waiting_room", pk=game.pk)
    if game.players.count() < 2:
        messages.error(request, "Il manque un second joueur.")
        return redirect("game:waiting_room", pk=game.pk)

    game_engine.start_game(game)
    return redirect("game:board", pk=game.pk)


@login_required
def game_detail(request, game_id):
    game = get_object_or_404(Game, pk=game_id, players__user=request.user)

    if game.status == Game.Status.WAITING:
        return redirect("game:waiting_room", pk=game.pk)
    if game.status == Game.Status.IN_PROGRESS:
        return redirect("game:board", pk=game.pk)
    return redirect("game:result", pk=game.pk)


@login_required
def game_board(request, pk):
    game = get_object_or_404(Game, pk=pk, players__user=request.user)

    if game.status == Game.Status.WAITING:
        return redirect("game:waiting_room", pk=game.pk)
    if game.status == Game.Status.FINISHED:
        return redirect("game:result", pk=game.pk)

    current_player = game.players.get(user=request.user)
    opponent = game.players.exclude(user=request.user).first()
    current_round = game.rounds.filter(number=game.current_round).first()

    if current_round is None:
        return redirect("game:waiting_room", pk=game.pk)

    my_field = (
        "player_one_card"
        if current_player.position == GamePlayer.Position.PLAYER_ONE
        else "player_two_card"
    )
    opp_field = (
        "player_two_card"
        if current_player.position == GamePlayer.Position.PLAYER_ONE
        else "player_one_card"
    )

    my_card = getattr(current_round, my_field)
    opponent_card = getattr(current_round, opp_field)
    last_round = game.rounds.filter(is_resolved=True).order_by("-number").first()

    context = {
        "game": game,
        "current_round": current_round,
        "current_player": current_player,
        "opponent": opponent,
        "can_play": my_card is None,
        "waiting_for_opponent": my_card is not None and not current_round.is_resolved,
        "displayed_player_card": my_card,
        "displayed_opponent_card": opponent_card if current_round.is_resolved else None,
        "last_round": last_round,
    }
    return render(request, "game/game_board.html", context)


@login_required
@require_POST
def play_card(request, pk):
    game = get_object_or_404(Game, pk=pk, players__user=request.user)
    current_player = game.players.get(user=request.user)

    try:
        game_engine.play_card(game, current_player)
    except ValueError as exc:
        messages.error(request, str(exc))

    if game.status == Game.Status.FINISHED:
        return redirect("game:result", pk=game.pk)
    return redirect("game:board", pk=game.pk)


@login_required
def game_result(request, pk):
    game = get_object_or_404(
        Game,
        pk=pk,
        players__user=request.user,
        status=Game.Status.FINISHED,
    )
    current_player = game.players.get(user=request.user)
    opponent = game.players.exclude(user=request.user).first()

    if game.winner_id is None:
        outcome = "draw"
    elif game.winner_id == current_player.pk:
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

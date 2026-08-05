from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Card, Deck, DeckCard, Game, GamePlayer, MoveLog, Profile, Round

User = get_user_model()
TOTAL_ROUNDS = 26
CARDS_PER_PLAYER = 26


class GameRuleError(ValueError):
    """Erreur métier renvoyée lorsqu'une action de jeu est interdite."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _require_authenticated(user) -> None:
    if not user.is_authenticated:
        raise GameRuleError("Un utilisateur authentifié est nécessaire.", status_code=403)


def _log(game: Game, action: str, player=None, round_obj=None, details=None) -> None:
    MoveLog.objects.create(
        game=game,
        player=player,
        round=round_obj,
        action=action,
        details=details or {},
    )


def _ensure_standard_cards() -> None:
    existing = set(Card.objects.values_list("suit", "rank"))
    cards = [
        Card(suit=suit, rank=rank)
        for suit, _ in Card.Suit.choices
        for rank, _ in Card.Rank.choices
        if (suit, rank) not in existing
    ]
    if cards:
        Card.objects.bulk_create(cards, ignore_conflicts=True)


def _get_player(game: Game, user: User) -> GamePlayer:
    try:
        return GamePlayer.objects.select_related("user").get(game=game, user=user)
    except GamePlayer.DoesNotExist as exc:
        raise GameRuleError(
            "Cet utilisateur ne participe pas à cette partie.",
            status_code=403,
        ) from exc


def _get_current_round(game: Game) -> Round:
    try:
        return (
            Round.objects.select_for_update()
            .get(game=game, number=game.current_round)
        )
    except Round.DoesNotExist as exc:
        raise GameRuleError("La manche courante est introuvable.") from exc


def _next_expected_position(round_obj: Round) -> int:
    if round_obj.player_one_card_id is None:
        return GamePlayer.Position.PLAYER_ONE
    if round_obj.player_two_card_id is None:
        return GamePlayer.Position.PLAYER_TWO
    raise GameRuleError("La manche courante est déjà complète.", status_code=409)


def _assign_cards(deck: Deck, player_one: GamePlayer, player_two: GamePlayer) -> None:
    ordered_cards = deck.shuffle()
    now = timezone.now()
    deck.shuffled_at = now
    deck.save(update_fields=["shuffled_at"])

    deck_cards = []
    for index, card in enumerate(ordered_cards[:CARDS_PER_PLAYER], start=1):
        deck_cards.append(DeckCard(deck=deck, card=card, owner=player_one, position=index))

    for index, card in enumerate(ordered_cards[CARDS_PER_PLAYER:], start=1):
        deck_cards.append(DeckCard(deck=deck, card=card, owner=player_two, position=index))

    DeckCard.objects.bulk_create(deck_cards)


@transaction.atomic
def create_game(user) -> Game:
    """Crée une partie et inscrit son créateur comme joueur 1."""

    _require_authenticated(user)

    game = Game.objects.create()
    player = GamePlayer.objects.create(
        game=game,
        user=user,
        position=GamePlayer.Position.PLAYER_ONE,
    )
    Profile.objects.get_or_create(user=user)
    _log(game, MoveLog.Action.GAME_CREATED, player=player)
    return game


@transaction.atomic
def join_game(game: Game, user) -> GamePlayer:
    """Ajoute un utilisateur comme joueur 2 dans une partie en attente."""

    _require_authenticated(user)
    locked_game = Game.objects.select_for_update().get(pk=game.pk)

    if locked_game.status != Game.Status.WAITING:
        raise GameRuleError("Seule une partie en attente peut être rejointe.", status_code=409)

    if GamePlayer.objects.filter(game=locked_game, user=user).exists():
        raise GameRuleError("Cet utilisateur participe déjà à cette partie.", status_code=409)

    players_count = GamePlayer.objects.select_for_update().filter(game=locked_game).count()
    if players_count == 0:
        raise GameRuleError("Cette partie ne possède pas de joueur 1.", status_code=409)
    if players_count >= 2:
        raise GameRuleError("Cette partie est déjà complète.", status_code=409)

    player = GamePlayer.objects.create(
        game=locked_game,
        user=user,
        position=GamePlayer.Position.PLAYER_TWO,
    )
    Profile.objects.get_or_create(user=user)
    _log(locked_game, MoveLog.Action.PLAYER_JOINED, player=player)
    return player


@transaction.atomic
def start_game(game: Game) -> Game:
    """Démarre la partie, crée le paquet, mélange et distribue les cartes."""

    locked_game = Game.objects.select_for_update().get(pk=game.pk)
    if locked_game.status != Game.Status.WAITING:
        raise GameRuleError("Seule une partie en attente peut être démarrée.", status_code=409)

    players = list(
        GamePlayer.objects.select_for_update()
        .select_related("user")
        .filter(game=locked_game)
        .order_by("position")
    )
    if len(players) != 2:
        raise GameRuleError("La partie doit contenir exactement deux joueurs.")
    if players[0].position != GamePlayer.Position.PLAYER_ONE:
        raise GameRuleError("La position du joueur 1 est obligatoire.")
    if players[1].position != GamePlayer.Position.PLAYER_TWO:
        raise GameRuleError("La position du joueur 2 est obligatoire.")

    if hasattr(locked_game, "deck") or DeckCard.objects.filter(deck__game=locked_game).exists():
        raise GameRuleError(
            "Les cartes ont déjà été distribuées pour cette partie.",
            status_code=409,
        )

    _ensure_standard_cards()
    deck = Deck.objects.create(game=locked_game)
    _assign_cards(deck, players[0], players[1])

    player_one_count = DeckCard.objects.filter(deck=deck, owner=players[0]).count()
    player_two_count = DeckCard.objects.filter(deck=deck, owner=players[1]).count()
    if player_one_count != CARDS_PER_PLAYER or player_two_count != CARDS_PER_PLAYER:
        raise GameRuleError("La distribution doit attribuer exactement 26 cartes à chaque joueur.")

    first_round = Round.objects.create(game=locked_game, number=1)
    locked_game.status = Game.Status.IN_PROGRESS
    locked_game.current_round = 1
    locked_game.started_at = timezone.now()
    locked_game.save(update_fields=["status", "current_round", "started_at"])

    _log(locked_game, MoveLog.Action.GAME_STARTED, round_obj=first_round)
    return locked_game


@transaction.atomic
def play_card(game: Game, user) -> Round:
    """Traite un clic 'Ajouter une carte' pour le joueur connecté."""

    _require_authenticated(user)
    locked_game = Game.objects.select_for_update().get(pk=game.pk)

    if locked_game.status == Game.Status.FINISHED:
        raise GameRuleError("Cette partie est terminée.", status_code=409)
    if locked_game.status != Game.Status.IN_PROGRESS:
        raise GameRuleError("La partie n'est pas en cours.", status_code=409)

    player = _get_player(locked_game, user)
    round_obj = _get_current_round(locked_game)

    if round_obj.is_resolved:
        raise GameRuleError("La manche courante est déjà résolue.")

    expected_position = _next_expected_position(round_obj)
    if player.position != expected_position:
        raise GameRuleError("Ce n'est pas au tour de ce joueur.", status_code=403)

    if round_obj.card_for(player) is not None:
        raise GameRuleError(
            "Ce joueur a déjà ajouté une carte pour cette manche.",
            status_code=409,
        )

    deck = Deck.objects.select_for_update().get(game=locked_game)
    deck_card = deck.draw(player)
    if deck_card is None:
        raise GameRuleError("Aucune carte non jouée disponible pour ce joueur.")

    deck_card.is_played = True
    deck_card.played_at = timezone.now()
    deck_card.save(update_fields=["is_played", "played_at"])

    if player.position == GamePlayer.Position.PLAYER_ONE:
        round_obj.player_one_card = deck_card
        round_obj.save(update_fields=["player_one_card"])
        _log(
            locked_game,
            MoveLog.Action.CARD_PLAYED,
            player=player,
            round_obj=round_obj,
            details={"position": deck_card.position},
        )
        return round_obj

    round_obj.player_two_card = deck_card
    round_obj.save(update_fields=["player_two_card"])
    _log(
        locked_game,
        MoveLog.Action.CARD_PLAYED,
        player=player,
        round_obj=round_obj,
        details={"position": deck_card.position},
    )

    _resolve_round(locked_game, round_obj)
    return round_obj


def _resolve_round(game: Game, round_obj: Round) -> None:
    player_one_card = round_obj.player_one_card
    player_two_card = round_obj.player_two_card
    if player_one_card is None or player_two_card is None:
        raise GameRuleError("Deux cartes sont nécessaires pour résoudre une manche.")

    winner = None
    if player_one_card.card.rank > player_two_card.card.rank:
        winner = player_one_card.owner
    elif player_two_card.card.rank > player_one_card.card.rank:
        winner = player_two_card.owner

    if winner is not None:
        GamePlayer.objects.filter(pk=winner.pk).update(score=F("score") + 1)
        winner.refresh_from_db()

    round_obj.winner = winner
    round_obj.is_resolved = True
    round_obj.resolved_at = timezone.now()
    round_obj.save(update_fields=["winner", "is_resolved", "resolved_at"])

    _log(
        game,
        MoveLog.Action.ROUND_RESOLVED,
        player=winner,
        round_obj=round_obj,
        details={"draw": winner is None},
    )

    if round_obj.number >= TOTAL_ROUNDS:
        _finish_game(game)
        return

    next_number = round_obj.number + 1
    Round.objects.create(game=game, number=next_number)
    game.current_round = next_number
    game.save(update_fields=["current_round"])


def _finish_game(game: Game) -> None:
    players = list(GamePlayer.objects.select_for_update().filter(game=game).order_by("position"))
    if len(players) != 2:
        raise GameRuleError("Impossible de terminer une partie sans deux joueurs.")

    winner = None
    if players[0].score > players[1].score:
        winner = players[0]
    elif players[1].score > players[0].score:
        winner = players[1]

    game.status = Game.Status.FINISHED
    game.current_round = TOTAL_ROUNDS
    game.winner = winner
    game.finished_at = timezone.now()
    game.save(update_fields=["status", "current_round", "winner", "finished_at"])

    if game.stats_recorded_at is None:
        for player in players:
            profile, _ = Profile.objects.select_for_update().get_or_create(user=player.user)
            profile.games_played = F("games_played") + 1
            profile.total_score = F("total_score") + player.score
            if winner is not None and player.pk == winner.pk:
                profile.games_won = F("games_won") + 1
            profile.save(update_fields=["games_played", "games_won", "total_score", "updated_at"])

        game.stats_recorded_at = timezone.now()
        game.save(update_fields=["stats_recorded_at"])

    _log(
        game,
        MoveLog.Action.GAME_FINISHED,
        player=winner,
        details={"draw": winner is None},
    )

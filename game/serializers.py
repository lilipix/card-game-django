from .models import DeckCard, Game, GamePlayer, Round


def _serialize_card(deck_card: DeckCard | None) -> dict | None:
    if deck_card is None:
        return None
    deck_card_id = deck_card.id  # pyright: ignore[reportAttributeAccessIssue]
    return {
        "id": deck_card_id,
        "suit": deck_card.card.suit,
        "suit_label": deck_card.card.get_suit_display(),  # pyright: ignore[reportAttributeAccessIssue]
        "rank": deck_card.card.rank,
        "rank_label": deck_card.card.get_rank_display(),  # pyright: ignore[reportAttributeAccessIssue]
    }


def _serialize_public_card_state(has_card: bool) -> dict:
    # Marqueur public: indique qu'une carte existe sans révéler son identité.
    return {"added": has_card}


def serialize_game_for_user(game: Game, user) -> dict:
    """Expose l'état de partie visible par l'utilisateur connecté."""

    players = list(
        GamePlayer.objects.select_related("user")
        .filter(game=game)
        .order_by("position")
    )
    user_id = user.id  # pyright: ignore[reportAttributeAccessIssue]
    # Les attributs *_id sont ajoutés dynamiquement par l'ORM Django.
    current_player = next(
        (
            player
            for player in players
            if player.user_id  # pyright: ignore[reportAttributeAccessIssue]
            == user_id
        ),
        None,
    )

    rounds = list(
        Round.objects.select_related(
            "player_one_card__card",
            "player_one_card__owner",
            "player_two_card__card",
            "player_two_card__owner",
            "winner__user",
        )
        .filter(game=game)
        .order_by("number")
    )

    game_id = game.id  # pyright: ignore[reportAttributeAccessIssue]
    return {
        "id": game_id,
        "status": game.status,
        "current_round": game.current_round,
        "winner": _serialize_winner(game.winner),
        "players": [_serialize_player(player) for player in players],
        "rounds": [_serialize_round(round_obj, current_player) for round_obj in rounds],
    }


def _serialize_player(player: GamePlayer) -> dict:
    player_id = player.id  # pyright: ignore[reportAttributeAccessIssue]
    return {
        "id": player_id,
        "username": player.user.get_username(),
        "position": player.position,
        "score": player.score,
    }


def _serialize_winner(player: GamePlayer | None) -> dict | None:
    if player is None:
        return None
    player_id = player.id  # pyright: ignore[reportAttributeAccessIssue]
    return {
        "id": player_id,
        "username": player.user.get_username(),
        "position": player.position,
    }


def _serialize_round(round_obj: Round, current_player: GamePlayer | None) -> dict:
    player_one_card_id = (
        round_obj.player_one_card_id  # pyright: ignore[reportAttributeAccessIssue]
    )
    player_two_card_id = (
        round_obj.player_two_card_id  # pyright: ignore[reportAttributeAccessIssue]
    )
    # Une carte est visible par son propriétaire dès son clic, puis par tous
    # uniquement après résolution de la manche.
    player_one_visible = round_obj.is_resolved or (
        current_player is not None
        and current_player.position == GamePlayer.Position.PLAYER_ONE
        and player_one_card_id is not None
    )
    player_two_visible = round_obj.is_resolved or (
        current_player is not None
        and current_player.position == GamePlayer.Position.PLAYER_TWO
        and player_two_card_id is not None
    )

    round_id = round_obj.id  # pyright: ignore[reportAttributeAccessIssue]
    return {
        "id": round_id,
        "number": round_obj.number,
        "is_resolved": round_obj.is_resolved,
        "winner": _serialize_winner(round_obj.winner) if round_obj.is_resolved else None,
        "player_one_card": (
            _serialize_card(round_obj.player_one_card)
            if player_one_visible
            else _serialize_public_card_state(player_one_card_id is not None)
        ),
        "player_two_card": (
            _serialize_card(round_obj.player_two_card)
            if player_two_visible
            else _serialize_public_card_state(player_two_card_id is not None)
        ),
    }

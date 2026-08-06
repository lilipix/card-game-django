from django.core.cache import cache

from .models import Game, GamePlayer
from .serializers import serialize_game_for_user

# supression automatique de l'état après 5 min
GAME_STATE_CACHE_TIMEOUT = 300


# construction du du nom de la clé
def game_state_cache_key(game_id: int, user_id: int) -> str:
    return f"game:{game_id}:user:{user_id}:state"


# récupérer l'état en cache ou le créer si absent
def get_cached_game_state_for_user(game: Game, user) -> dict:
    """Récupère l'état depuis Redis ou le reconstruit depuis PostgreSQL."""

    game_id = game.pk
    user_id = user.pk
    cache_key = game_state_cache_key(game_id, user_id)

    state = cache.get(cache_key)

    if state is None:
        state = serialize_game_for_user(game, user)
        cache.set(
            cache_key,
            state,
            timeout=GAME_STATE_CACHE_TIMEOUT,
        )

    return state


# supprime les états périmés et les versions en cache
def invalidate_game_state(game_id: int) -> None:
    """Supprime les versions en cache pour tous les joueurs de la partie."""

    user_ids = GamePlayer.objects.filter(
        game_id=game_id,
    ).values_list("user_id", flat=True)

    cache_keys = [game_state_cache_key(game_id, user_id) for user_id in user_ids]

    if cache_keys:
        cache.delete_many(cache_keys)

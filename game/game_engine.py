# game/game_engine.py
from random import shuffle

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import Game, GameCard, GamePlayer, Round

User = get_user_model()


@transaction.atomic
def create_game(user) -> Game:
    """Crée une partie et inscrit son créateur comme joueur 1."""

    if not user.is_authenticated:
        raise ValueError("Un utilisateur authentifié est nécessaire pour créer une partie.")

    game = Game.objects.create()

    GamePlayer.objects.create(
        game=game,
        user=user,
        position=GamePlayer.Position.PLAYER_ONE,
    )

    return game


@transaction.atomic
def join_game(game: Game, user) -> GamePlayer:
    """Ajoute un utilisateur comme joueur 2 dans une partie en attente."""

    # Seul un utilisateur connecté peut rejoindre une partie.
    if not user.is_authenticated:
        raise ValueError("Un utilisateur authentifié est nécessaire pour rejoindre une partie.")

    # Verrouille la partie jusqu'à la fin de la transaction.
    # Cela évite que deux utilisateurs prennent la dernière place simultanément.
    locked_game = Game.objects.select_for_update().get(pk=game.pk)

    # Une partie déjà commencée ou terminée ne peut plus accueillir de joueur.
    if locked_game.status != Game.Status.WAITING:
        raise ValueError("Seule une partie en attente peut être rejointe.")

    # Un utilisateur ne peut occuper qu'une seule position dans une même partie.
    if GamePlayer.objects.filter(
        game=locked_game,
        user=user,
    ).exists():
        raise ValueError("Cet utilisateur participe déjà à cette partie.")

    # Une partie de bataille doit déjà avoir un créateur avant d'être rejointe.
    players_count = GamePlayer.objects.filter(
        game=locked_game,
    ).count()

    if players_count == 0:
        raise ValueError("Cette partie ne possède pas de joueur 1.")

    # La partie est limitée à deux participants.
    if players_count >= 2:
        raise ValueError("Cette partie est déjà complète.")

    # Renvoie un message si position déjà occupée, contrainte d'unicité gérée par la bdd
    if GamePlayer.objects.filter(
        game=locked_game,
        position=GamePlayer.Position.PLAYER_TWO,
    ).exists():
        raise ValueError("La position du joueur 2 est déjà occupée.")

    # Le nouvel utilisateur prend obligatoirement la deuxième position.
    # Son score initial utilise la valeur par défaut définie dans le modèle.
    player = GamePlayer.objects.create(
        game=locked_game,
        user=user,
        position=GamePlayer.Position.PLAYER_TWO,
    )

    # Le participant créé pourra être utilisé par la vue appelante.
    return player


@transaction.atomic
def start_game(game: Game) -> Game:
    """Lancer la partie et distribue 26 cartes à chaque joueur."""

    # Récupère et verrouille la partie pendant toute l'opération.
    # Cela empêche deux démarrages simultanés.
    locked_game = Game.objects.select_for_update().get(pk=game.pk)

    # Seule une partie encore en attente peut être démarrée.
    if locked_game.status != Game.Status.WAITING:
        raise ValueError("Seule une partie en attente peut être démarrée.")

    # Récupère le joueur 1.
    player_one = GamePlayer.objects.filter(
        game=locked_game,
        position=GamePlayer.Position.PLAYER_ONE,
    ).first()

    # Récupère le joueur 2.
    player_two = GamePlayer.objects.filter(
        game=locked_game,
        position=GamePlayer.Position.PLAYER_TWO,
    ).first()

    # La partie ne peut démarrer que lorsque les deux joueurs sont présents.
    if player_one is None or player_two is None:
        raise ValueError("Deux joueurs sont nécessaires pour démarrer la partie.")

    # Protection contre une éventuelle incohérence en base.
    players_count = GamePlayer.objects.filter(
        game=locked_game,
    ).count()

    if players_count != 2:
        raise ValueError("La partie doit contenir exactement deux joueurs.")

    # Empêche de distribuer une deuxième fois les cartes.
    if GameCard.objects.filter(game=locked_game).exists():
        raise ValueError("Les cartes ont déjà été distribuées pour cette partie.")

    # Construit les 52 combinaisons possibles :
    # 4 enseignes multipliées par 13 valeurs.
    deck = [(suit, rank) for suit, _ in GameCard.Suit.choices for rank, _ in GameCard.Rank.choices]

    # Mélange la liste en mémoire avant la distribution.
    shuffle(deck)

    # Distribue les 26 premières cartes au joueur 1
    # et les 26 suivantes au joueur 2.
    cards_to_create = []

    for index, (suit, rank) in enumerate(deck[:26], start=1):
        cards_to_create.append(
            GameCard(
                game=locked_game,
                owner=player_one,
                suit=suit,
                rank=rank,
                position=index,
            )
        )

    for index, (suit, rank) in enumerate(deck[26:], start=1):
        cards_to_create.append(
            GameCard(
                game=locked_game,
                owner=player_two,
                suit=suit,
                rank=rank,
                position=index,
            )
        )

    # Enregistre les 52 cartes en une seule requête SQL.
    GameCard.objects.bulk_create(cards_to_create)

    # Crée la première manche, encore vide.
    Round.objects.create(
        game=locked_game,
        number=1,
    )

    # La partie est maintenant prête à être jouée.
    locked_game.status = Game.Status.IN_PROGRESS
    locked_game.current_round = 1
    locked_game.started_at = timezone.now()

    # Ne met à jour que les champs réellement modifiés.
    locked_game.save(
        update_fields=[
            "status",
            "current_round",
            "started_at",
        ]
    )

    return locked_game

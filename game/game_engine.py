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


@transaction.atomic
def play_card(game: Game, player: GamePlayer) -> GameCard:
    """Joue la prochaine carte disponible d'un joueur."""

    # Récupère la partie depuis la base et verrouille sa ligne
    # pendant toute la transaction pour éviter deux actions simultanées.
    current_game = Game.objects.select_for_update().get(pk=game.pk)

    # Une carte ne peut être jouée que si la partie a commencé.
    if current_game.status != Game.Status.IN_PROGRESS:
        raise ValueError("Une partie doit être démarrée pour jouer.")

    # Recherche le joueur reçu dans les participants de cette partie.
    # On ne se fie pas uniquement à l'objet player passé à la fonction.
    current_player = GamePlayer.objects.filter(
        pk=player.pk,
        game=current_game,
    ).first()

    # Refuse l'action si le joueur n'appartient pas à la partie.
    if current_player is None:
        raise ValueError("Ce joueur ne participe pas à cette partie.")

    # Récupère la manche correspondant au numéro actuel de la partie.
    current_round = Round.objects.filter(
        game=current_game,
        number=current_game.current_round,
    ).first()

    # Cette situation indique une incohérence dans les données.
    if current_round is None:
        raise ValueError("La manche actuelle est introuvable.")

    # Une manche résolue ne doit plus accepter de nouvelles cartes.
    if current_round.is_resolved:
        raise ValueError("Cette manche est déjà terminée.")

    # Vérifie que le joueur 1 n'a pas déjà posé sa carte.
    if current_player.position == GamePlayer.Position.PLAYER_ONE:
        if current_round.player_one_card is not None:
            raise ValueError("Le joueur 1 a déjà joué pendant cette manche.")

    # Vérifie que le joueur 2 n'a pas déjà posé sa carte.
    elif current_player.position == GamePlayer.Position.PLAYER_TWO:
        if current_round.player_two_card is not None:
            raise ValueError("Le joueur 2 a déjà joué pendant cette manche.")

    # Sécurité supplémentaire si une position incorrecte existe en base.
    else:
        raise ValueError("La position du joueur est invalide.")

    # Récupère et verrouille la première carte non jouée du joueur.
    # L'ordre par position respecte l'ordre obtenu lors de la distribution.
    card = (
        GameCard.objects.select_for_update()
        .filter(
            game=current_game,
            owner=current_player,
            is_played=False,
        )
        .order_by("position")
        .first()
    )

    # Refuse l'action si toutes les cartes du joueur ont déjà été jouées.
    if card is None:
        raise ValueError("Ce joueur n'a plus de carte à jouer.")

    # Place la carte dans le champ correspondant à la position du joueur.
    if current_player.position == GamePlayer.Position.PLAYER_ONE:
        current_round.player_one_card = card
        current_round.save(update_fields=["player_one_card"])
    else:
        current_round.player_two_card = card
        current_round.save(update_fields=["player_two_card"])

    # Empêche cette carte d'être sélectionnée lors d'une manche suivante.
    card.is_played = True
    card.save(update_fields=["is_played"])

    # Recharge la manche depuis la base pour récupérer les deux cartes.
    current_round.refresh_from_db()

    # Lorsque les deux joueurs ont joué, la manche est automatiquement résolue.
    if current_round.player_one_card is not None and current_round.player_two_card is not None:
        resolve_round(current_round)

    # Retourne la carte jouée, même si la manche vient d'être résolue.
    return card


@transaction.atomic
def resolve_round(round_to_resolve: Round) -> Round:
    """Résout une manche et prépare la suite de la partie."""

    # Récupère et verrouille la manche afin d'empêcher
    # deux résolutions simultanées.
    current_round = (
        Round.objects.select_for_update()
        .select_related(
            "game",
            "player_one_card",
            "player_two_card",
        )
        .get(pk=round_to_resolve.pk)
    )

    # Une manche déjà résolue ne peut pas l'être une seconde fois.
    if current_round.is_resolved:
        raise ValueError("Cette manche est déjà terminée.")

    # Les deux joueurs doivent avoir posé leur carte.
    if current_round.player_one_card is None or current_round.player_two_card is None:
        raise ValueError("Les deux joueurs doivent avoir joué avant de résoudre la manche.")

    # Récupère la valeur numérique de chaque carte.
    # Le rang est compris entre 2 et 14, l'As ayant la valeur 14.
    player_one_rank = current_round.player_one_card.rank
    player_two_rank = current_round.player_two_card.rank

    # Récupère et verrouille les deux joueurs avant de modifier leur score.
    player_one = GamePlayer.objects.select_for_update().get(
        game=current_round.game,
        position=GamePlayer.Position.PLAYER_ONE,
    )

    player_two = GamePlayer.objects.select_for_update().get(
        game=current_round.game,
        position=GamePlayer.Position.PLAYER_TWO,
    )

    # Compare les deux cartes et attribue un point au gagnant.
    if player_one_rank > player_two_rank:
        player_one.score += 1
        player_one.save(update_fields=["score"])
        current_round.winner = player_one

    elif player_two_rank > player_one_rank:
        player_two.score += 1
        player_two.save(update_fields=["score"])
        current_round.winner = player_two

    else:
        # En cas d'égalité, aucun joueur ne gagne de point.
        # Les deux cartes restent retirées du jeu puisqu'elles
        # ont déjà été marquées comme jouées dans play_card().
        current_round.winner = None

    # Termine officiellement la manche et enregistre sa date de résolution.
    current_round.is_resolved = True
    current_round.resolved_at = timezone.now()

    current_round.save(
        update_fields=[
            "winner",
            "is_resolved",
            "resolved_at",
        ]
    )

    # Après la manche 26, toutes les cartes ont été jouées :
    # la partie doit donc être terminée.
    if current_round.number == 26:
        finish_game(current_round.game)

    else:
        # Calcule et enregistre le numéro de la prochaine manche.
        next_round_number = current_round.number + 1

        current_round.game.current_round = next_round_number
        current_round.game.save(update_fields=["current_round"])

        # Crée une nouvelle manche vide pour accueillir
        # les prochaines cartes des deux joueurs.
        Round.objects.create(
            game=current_round.game,
            number=next_round_number,
        )

    # Retourne la manche résolue afin que la vue puisse exploiter le résultat.
    return current_round


@transaction.atomic
def finish_game(game: Game) -> Game:
    """Termine une partie après la résolution des 26 manches."""

    # Récupère la version actuelle de la partie et verrouille sa ligne
    # afin d'empêcher deux terminaisons simultanées.
    current_game = Game.objects.select_for_update().get(pk=game.pk)

    # Seule une partie en cours peut être terminée.
    if current_game.status != Game.Status.IN_PROGRESS:
        raise ValueError("Seule une partie en cours peut être terminée.")

    # Vérifie que la dernière manche a bien été atteinte.
    if current_game.current_round != 26:
        raise ValueError("La partie ne peut pas être terminée avant la manche 26.")

    # Vérifie que la dernière manche existe et qu'elle est résolue.
    last_round = Round.objects.filter(
        game=current_game,
        number=26,
        is_resolved=True,
    ).first()

    if last_round is None:
        raise ValueError("La dernière manche doit être résolue avant de terminer la partie.")

    # Récupère et verrouille les deux joueurs avant de comparer leurs scores.
    player_one = GamePlayer.objects.select_for_update().get(
        game=current_game,
        position=GamePlayer.Position.PLAYER_ONE,
    )

    player_two = GamePlayer.objects.select_for_update().get(
        game=current_game,
        position=GamePlayer.Position.PLAYER_TWO,
    )

    # Le joueur ayant le score le plus élevé remporte la partie.
    if player_one.score > player_two.score:
        current_game.winner = player_one  # type: ignore[reportAttributeAccessIssue]

    elif player_two.score > player_one.score:
        current_game.winner = player_two  # type: ignore[reportAttributeAccessIssue]

    else:
        # Si les scores sont identiques, la partie se termine
        # par un match nul et ne possède donc aucun gagnant.
        current_game.winner = None

    # Termine officiellement la partie et enregistre sa date de fin.
    current_game.status = Game.Status.FINISHED
    current_game.finished_at = timezone.now()

    current_game.save(
        update_fields=[
            "winner",
            "status",
            "finished_at",
        ]
    )

    # Retourne la partie terminée avec son résultat final.
    return current_game

# game/tests/test_game_engine.py

from django.contrib.auth import get_user_model
from django.test import TestCase

from game.game_engine import (
    GameRuleError,
    create_game,
    join_game,
    play_card,
    start_game,
    _resolve_round as resolve_round,
)
from game.models import Game, GameCard, GamePlayer, Round

User = get_user_model()


class CreateGameTests(TestCase):

    def setUp(self):
        """Initialisation des utilisateurs de test."""
        self.user1 = User.objects.create_user(username="player1", password="password123")
        self.user2 = User.objects.create_user(username="player2", password="password123")
        self.user3 = User.objects.create_user(username="player3", password="password123")

    # -------------------------------------------------------------------------
    # TESTS : join_game
    # -------------------------------------------------------------------------

    def test_join_game_success(self):
        """Vérifie qu'un deuxième joueur peut rejoindre une partie en attente."""
        game = create_game(self.user1)
        player_two = join_game(game, self.user2)

        self.assertEqual(GamePlayer.objects.count(), 2)
        self.assertEqual(player_two.user, self.user2)
        self.assertEqual(player_two.position, GamePlayer.Position.PLAYER_TWO)

    def test_join_game_same_user_raises_error(self):
        """Vérifie qu'un utilisateur ne peut pas rejoindre sa propre partie."""
        game = create_game(self.user1)
        with self.assertRaisesMessage(
            ValueError, "Cet utilisateur participe déjà à cette partie."
        ):
            join_game(game, self.user1)

    def test_join_game_already_full_raises_error(self):
        """Vérifie qu'un troisième joueur ne peut pas rejoindre une partie complète."""
        game = create_game(self.user1)
        join_game(game, self.user2)

        with self.assertRaisesMessage(ValueError, "Cette partie est déjà complète."):
            join_game(game, self.user3)

    # -------------------------------------------------------------------------
    # TESTS : start_game
    # -------------------------------------------------------------------------

    def test_start_game_success(self):
        """Vérifie la distribution des 52 cartes et l'initialisation de la manche 1."""
        game = create_game(self.user1)
        join_game(game, self.user2)

        started_game = start_game(game)

        # Statut et manches
        self.assertEqual(started_game.status, Game.Status.IN_PROGRESS)
        self.assertEqual(started_game.current_round, 1)
        self.assertTrue(Round.objects.filter(game=started_game, number=1).exists())

        # Distribution des cartes (via l'owner pour filtrer les cartes de cette partie)
        self.assertEqual(GameCard.objects.filter(owner__game=started_game).count(), 52)

        p1 = GamePlayer.objects.get(game=started_game, position=GamePlayer.Position.PLAYER_ONE)
        p2 = GamePlayer.objects.get(game=started_game, position=GamePlayer.Position.PLAYER_TWO)

        self.assertEqual(GameCard.objects.filter(owner=p1).count(), 26)
        self.assertEqual(GameCard.objects.filter(owner=p2).count(), 26)

    def test_start_game_without_two_players_raises_error(self):
        """Vérifie qu'une partie ne peut pas démarrer avec un seul joueur."""
        game = create_game(self.user1)
        with self.assertRaisesMessage(
            GameRuleError, "La partie doit contenir exactement deux joueurs."
        ):
            start_game(game)

    # -------------------------------------------------------------------------
    # TESTS : play_card & resolve_round
    # -------------------------------------------------------------------------

    def test_play_card_and_automatic_resolution(self):
        """Vérifie le cycle de jeu d'une manche et sa résolution automatique."""
        game = create_game(self.user1)
        join_game(game, self.user2)
        start_game(game)

        p1 = GamePlayer.objects.get(game=game, position=GamePlayer.Position.PLAYER_ONE)
        p2 = GamePlayer.objects.get(game=game, position=GamePlayer.Position.PLAYER_TWO)

        # Joueur 1 joue une carte (play_card retourne l'objet Round)
        round_obj = play_card(game, p1.user)
        current_round = Round.objects.get(game=game, number=1)

        self.assertIsNotNone(current_round.player_one_card)
        self.assertFalse(current_round.is_resolved)  # Pas encore résolu

        # Joueur 2 joue une carte -> Déclenche automatiquement resolve_round()
        play_card(game, p2.user)
        current_round.refresh_from_db()

        self.assertIsNotNone(current_round.player_two_card)
        self.assertTrue(current_round.is_resolved)

        # La manche suivante doit être créée et le compteur incrémenté
        game.refresh_from_db()
        self.assertEqual(game.current_round, 2)
        self.assertTrue(Round.objects.filter(game=game, number=2).exists())

    def test_play_card_twice_same_round_raises_error(self):
        """Vérifie qu'un même joueur ne peut pas rejouer dans la même manche."""
        game = create_game(self.user1)
        join_game(game, self.user2)
        start_game(game)

        p1 = GamePlayer.objects.get(game=game, position=GamePlayer.Position.PLAYER_ONE)
        play_card(game, p1.user)

        with self.assertRaisesMessage(
            GameRuleError, "Ce n'est pas au tour de ce joueur."
        ):
            play_card(game, p1.user)

    # -------------------------------------------------------------------------
    # TESTS : finish_game
    # -------------------------------------------------------------------------

    def test_finish_game_determines_winner(self):
        """Vérifie qu'une partie se termine correctement après la 26e manche."""
        game = create_game(self.user1)
        join_game(game, self.user2)
        start_game(game)

        p1 = GamePlayer.objects.get(game=game, position=GamePlayer.Position.PLAYER_ONE)
        p2 = GamePlayer.objects.get(game=game, position=GamePlayer.Position.PLAYER_TWO)

        # Simulation du passage direct à la manche 26
        game.current_round = 26
        game.save()

        round_26 = Round.objects.create(game=game, number=26)

        # Récupération de cartes existantes distribuées à p1 et p2
        card1 = GameCard.objects.filter(owner=p1, is_played=False).first()
        card2 = GameCard.objects.filter(owner=p2, is_played=False).first()

        round_26.player_one_card = card1
        round_26.player_two_card = card2
        round_26.save()

        # Résolution de la manche 26 (qui appelle automatiquement finish_game)
        resolve_round(game, round_26)

        game.refresh_from_db()

        self.assertEqual(game.status, Game.Status.FINISHED)
        self.assertIsNotNone(game.winner)
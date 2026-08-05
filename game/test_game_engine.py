# game/tests/test_game_engine.py

from django.contrib.auth import get_user_model
from django.test import TestCase

from game.game_engine import create_game
from game.models import Game, GamePlayer

User = get_user_model()


class CreateGameTests(TestCase):
    def test_create_game_creates_waiting_game(self):
        user = User.objects.create_user(
            username="alice",
            password="password123",
        )

        game = create_game(user)

        self.assertEqual(Game.objects.count(), 1)
        self.assertEqual(game.status, Game.Status.WAITING)
        self.assertEqual(game.current_round, 0)
        self.assertIsNone(game.winner)

    def test_create_game_adds_creator_as_player_one(self):
        user = User.objects.create_user(
            username="alice",
            password="password123",
        )

        game = create_game(user)

        player = GamePlayer.objects.get(game=game)

        self.assertEqual(player.user, user)
        self.assertEqual(
            player.position,
            GamePlayer.Position.PLAYER_ONE,
        )
        self.assertEqual(player.score, 0)
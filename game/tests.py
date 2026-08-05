from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from .models import Card, Deck, Game, GameCard, GamePlayer


class SettingsSmokeTests(SimpleTestCase):
    def test_static_files_are_configured(self):
        self.assertEqual(settings.STATIC_URL, "/static/")
        self.assertEqual(settings.STATIC_ROOT.name, "staticfiles")


class GamePlayerTests(TestCase):
    def test_remaining_cards_count_excludes_played_cards(self):
        User = get_user_model()
        user = User.objects.create_user(username="tester", password="Testpass123!")
        game = Game.objects.create()
        deck = Deck.objects.create(game=game)
        player = GamePlayer.objects.create(
            game=game,
            user=user,
            position=GamePlayer.Position.PLAYER_ONE,
        )

        ace_hearts, _ = Card.objects.get_or_create(
            suit=Card.Suit.HEARTS,
            rank=Card.Rank.ACE,
        )
        two_clubs, _ = Card.objects.get_or_create(
            suit=Card.Suit.CLUBS,
            rank=Card.Rank.TWO,
        )

        GameCard.objects.create(
            deck=deck,
            card=ace_hearts,
            owner=player,
            position=1,
        )
        GameCard.objects.create(
            deck=deck,
            card=two_clubs,
            owner=player,
            position=2,
            is_played=True,
        )

        self.assertEqual(player.remaining_cards_count, 1)

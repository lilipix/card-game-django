from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import Game, GamePlayer


class SettingsSmokeTests(SimpleTestCase):
    def test_static_files_are_configured(self):
        self.assertEqual(settings.STATIC_URL, "/static/")
        self.assertEqual(settings.STATIC_ROOT.name, "staticfiles")


class RouteCompatibilityTests(SimpleTestCase):
    def test_named_routes_resolve(self):
        self.assertEqual(reverse("game:game_list"), "/games/")
        self.assertEqual(reverse("game:game_create"), "/games/create/")
        self.assertEqual(reverse("game:game_join", args=[12]), "/games/12/join/")
        self.assertEqual(reverse("game:game_play_card", args=[12]), "/games/12/play-card/")
        self.assertEqual(reverse("game:game_state", args=[12]), "/games/12/state/")
        self.assertEqual(reverse("game:game_detail", args=[12]), "/games/12/")
        self.assertEqual(reverse("game:game_result", args=[12]), "/games/12/result/")
        self.assertEqual(reverse("game:home"), "/games/home/")
        self.assertEqual(reverse("game:signup"), "/games/signup/")


class WaitingRoomViewTests(TestCase):
    def test_creator_sees_waiting_room_with_player_slots(self):
        user_model = get_user_model()
        creator = user_model.objects.create_user(username="creator", password="Testpass123!")
        game = Game.objects.create(status=Game.Status.WAITING)
        GamePlayer.objects.create(
            game=game,
            user=creator,
            position=GamePlayer.Position.PLAYER_ONE,
        )

        self.client.force_login(creator)
        response = self.client.get(reverse("game:game_detail", args=[game.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "game/waiting_room.html")
        self.assertContains(response, "Joueur 1")
        self.assertContains(response, "Place libre")


class GameListViewTests(TestCase):
    def test_user_games_are_displayed_in_game_list(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(username="dina", password="Testpass123!")
        game = Game.objects.create(status=Game.Status.IN_PROGRESS)
        GamePlayer.objects.create(
            game=game,
            user=user,
            position=GamePlayer.Position.PLAYER_ONE,
        )

        self.client.force_login(user)
        response = self.client.get(reverse("game:game_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mes parties")
        self.assertContains(response, f"Partie #{game.id}")

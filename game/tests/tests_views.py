from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class GameViewsIntegrationTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="password123"
        )
        # Remplacez 'game_list' par le nom exact de votre vue/URL
        self.list_url = reverse("game:game_list")

    def test_anonymous_user_redirected_to_login(self):
        """Un utilisateur non connecté doit être redirigé vers la page de login."""
        response = self.client.get(self.list_url)
        # Redirection 302 vers le login
        self.assertEqual(response.status_code, 302)

    def test_authenticated_user_can_access_game_list(self):
        """Un utilisateur connecté peut accéder à la liste des parties."""
        self.client.login(username="testuser", password="password123")
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)

    def test_create_game_view_authenticated(self):
        """Un utilisateur connecté peut poster pour créer une partie."""
        self.client.login(username="testuser", password="password123")
        # Remplacez 'game_create' par le nom de votre URL de création
        create_url = reverse("game:game_create")
        response = self.client.post(create_url)

        # Vérifie qu'il y a bien une redirection après création (ex: vers la partie)
        self.assertIn(response.status_code, [200, 302])
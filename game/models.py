from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q


class Profile(models.Model):
    """Statistiques globales d'un utilisateur."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="game_profile",
    )
    games_played = models.PositiveIntegerField(default=0)
    games_won = models.PositiveIntegerField(default=0)
    total_score = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Profil jeu de {self.user}"


class Game(models.Model):
    """Partie de Bataille simplifiée entre deux joueurs."""

    class Status(models.TextChoices):
        WAITING = "WAITING", "En attente"
        IN_PROGRESS = "IN_PROGRESS", "En cours"
        FINISHED = "FINISHED", "Terminée"

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.WAITING,
    )
    current_round = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(26)],
    )
    winner = models.ForeignKey(
        "GamePlayer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="games_won",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    # Marqueur interne: les statistiques globales ne doivent être ajoutées qu'une fois.
    stats_recorded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(current_round__gte=0) & Q(current_round__lte=26),
                name="game_current_round_between_0_and_26",
            ),
        ]

    def __str__(self) -> str:
        return f"Partie {self.pk} - {self.get_status_display()}"  # pyright: ignore[reportAttributeAccessIssue]


class GamePlayer(models.Model):
    """Participation d'un utilisateur à une partie."""

    class Position(models.IntegerChoices):
        PLAYER_ONE = 1, "Joueur 1"
        PLAYER_TWO = 2, "Joueur 2"

    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="players",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="game_participations",
    )
    position = models.PositiveSmallIntegerField(choices=Position.choices)
    score = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(26)],
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["game", "user"],
                name="unique_user_per_game",
            ),
            models.UniqueConstraint(
                fields=["game", "position"],
                name="unique_player_position_per_game",
            ),
            models.CheckConstraint(
                condition=Q(position__in=[1, 2]),
                name="game_player_position_is_1_or_2",
            ),
            models.CheckConstraint(
                condition=Q(score__gte=0) & Q(score__lte=26),
                name="game_player_score_between_0_and_26",
            ),
        ]

    def __str__(self) -> str:
        game_id = self.game_id  # pyright: ignore[reportAttributeAccessIssue]
        return f"{self.user} - partie {game_id} - {self.get_position_display()}"  # pyright: ignore[reportAttributeAccessIssue]


class Card(models.Model):
    """Définition d'une carte standard."""

    class Suit(models.TextChoices):
        HEARTS = "HEARTS", "Coeur"
        DIAMONDS = "DIAMONDS", "Carreau"
        CLUBS = "CLUBS", "Trefle"
        SPADES = "SPADES", "Pique"

    class Rank(models.IntegerChoices):
        TWO = 2, "2"
        THREE = 3, "3"
        FOUR = 4, "4"
        FIVE = 5, "5"
        SIX = 6, "6"
        SEVEN = 7, "7"
        EIGHT = 8, "8"
        NINE = 9, "9"
        TEN = 10, "10"
        JACK = 11, "Valet"
        QUEEN = 12, "Dame"
        KING = 13, "Roi"
        ACE = 14, "As"

    suit = models.CharField(max_length=10, choices=Suit.choices)
    rank = models.PositiveSmallIntegerField(choices=Rank.choices)

    class Meta:
        ordering = ["suit", "rank"]
        constraints = [
            models.UniqueConstraint(
                fields=["suit", "rank"],
                name="unique_standard_card",
            ),
        ]

    @property
    def power(self) -> int:
        return self.rank

    def __str__(self) -> str:
        return f"{self.get_rank_display()} de {self.get_suit_display()}"  # pyright: ignore[reportAttributeAccessIssue]


class Deck(models.Model):
    """Paquet physique associé à une partie."""

    game = models.OneToOneField(
        Game,
        on_delete=models.CASCADE,
        related_name="deck",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    shuffled_at = models.DateTimeField(null=True, blank=True)

    def shuffle(self) -> list[Card]:
        """Retourne les 52 cartes standard mélangées côté serveur."""

        from random import shuffle

        cards = list(Card.objects.all())
        shuffle(cards)
        return cards

    def draw(self, owner: GamePlayer):
        """Pioche la première carte non jouée du joueur dans l'ordre serveur."""

        return (
            # Le verrou empêche deux requêtes concurrentes de piocher la même carte.
            self.cards.select_for_update()  # pyright: ignore[reportAttributeAccessIssue]
            .filter(owner=owner, is_played=False)
            .order_by("position")
            .first()
        )

    def __str__(self) -> str:
        game_id = self.game_id  # pyright: ignore[reportAttributeAccessIssue]
        return f"Paquet de la partie {game_id}"


class DeckCard(models.Model):
    """Carte physique distribuée dans le paquet d'un joueur."""

    # Contrairement à Card, DeckCard représente l'exemplaire attribué en partie.
    deck = models.ForeignKey(
        Deck,
        on_delete=models.CASCADE,
        related_name="cards",
    )
    card = models.ForeignKey(
        Card,
        on_delete=models.PROTECT,
        related_name="deck_cards",
    )
    owner = models.ForeignKey(
        GamePlayer,
        on_delete=models.CASCADE,
        related_name="deck_cards",
    )
    position = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(26)],
    )
    is_played = models.BooleanField(default=False)
    played_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["owner__position", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["deck", "card"],
                name="unique_physical_card_per_deck",
            ),
            models.UniqueConstraint(
                fields=["owner", "position"],
                name="unique_position_per_player_deck",
            ),
            models.CheckConstraint(
                condition=Q(position__gte=1) & Q(position__lte=26),
                name="deck_card_position_between_1_and_26",
            ),
        ]

    @property
    def rank(self) -> int:
        return self.card.rank

    def __str__(self) -> str:
        return f"{self.card} - {self.owner}"


class Round(models.Model):
    """Manche: une carte par joueur, résolution après le second clic."""

    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="rounds",
    )
    number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(26)],
    )
    player_one_card = models.ForeignKey(
        DeckCard,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="rounds_as_player_one_card",
    )
    player_two_card = models.ForeignKey(
        DeckCard,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="rounds_as_player_two_card",
    )
    # Null signifie "pas encore résolue" ou "égalité"; is_resolved fait la différence.
    winner = models.ForeignKey(
        GamePlayer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rounds_won",
    )
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(
                fields=["game", "number"],
                name="unique_round_number_per_game",
            ),
            models.CheckConstraint(
                condition=Q(number__gte=1) & Q(number__lte=26),
                name="round_number_between_1_and_26",
            ),
            models.CheckConstraint(
                condition=(
                    Q(player_one_card__isnull=True)
                    | Q(player_two_card__isnull=True)
                    | ~Q(player_one_card=F("player_two_card"))
                ),
                name="round_cards_must_be_different",
            ),
        ]

    @property
    def is_draw(self) -> bool:
        return self.is_resolved and self.winner is None

    def card_for(self, player: GamePlayer):
        if player.position == GamePlayer.Position.PLAYER_ONE:
            return self.player_one_card
        return self.player_two_card

    def __str__(self) -> str:
        game_id = self.game_id  # pyright: ignore[reportAttributeAccessIssue]
        return f"Manche {self.number} - partie {game_id}"


# Compatibilite avec l'ancien nom utilise par la migration initiale.
GameCard = DeckCard


class MoveLog(models.Model):
    """Journal chronologique des actions et événements d'une partie."""

    class Action(models.TextChoices):
        GAME_CREATED = "GAME_CREATED", "Partie creee"
        PLAYER_JOINED = "PLAYER_JOINED", "Joueur arrive"
        GAME_STARTED = "GAME_STARTED", "Partie demarree"
        CARD_PLAYED = "CARD_PLAYED", "Carte ajoutee"
        ROUND_RESOLVED = "ROUND_RESOLVED", "Manche resolue"
        GAME_FINISHED = "GAME_FINISHED", "Partie terminee"

    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="move_logs",
    )
    player = models.ForeignKey(
        GamePlayer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="move_logs",
    )
    round = models.ForeignKey(
        Round,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="move_logs",
    )
    action = models.CharField(max_length=30, choices=Action.choices)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["game", "created_at"]),
            models.Index(fields=["action"]),
        ]

    def __str__(self) -> str:
        game_id = self.game_id  # pyright: ignore[reportAttributeAccessIssue]
        return f"{self.get_action_display()} - partie {game_id}"  # pyright: ignore[reportAttributeAccessIssue]

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q


class Game(models.Model):
    """Représente une partie de Bataille simplifiée entre deux joueurs."""

    class Status(models.TextChoices):
        WAITING = "WAITING", "En attente"
        IN_PROGRESS = "IN_PROGRESS", "En cours"
        FINISHED = "FINISHED", "Terminée"

    # Etat global de la partie : attente des joueurs, partie en cours,
    # puis partie terminée lorsque les 26 manches ont été résolues.
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.WAITING,
    )

    # Progression de la partie. La Bataille simplifiée contient toujours
    # 26 manches, car chaque joueur reçoit 26 cartes.
    current_round = models.PositiveSmallIntegerField(
        default=0,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(26),
        ],
    )

    # Vainqueur final. Ce champ reste vide tant que la partie n'est pas finie
    # et reste aussi vide si la partie se termine par un match nul.
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

    def __str__(self):
        return f"Partie {self.pk} — {self.get_status_display()}"  # type: ignore[attr-defined]


class GamePlayer(models.Model):
    """Associe un utilisateur Django à une partie et conserve son score."""

    class Position(models.IntegerChoices):
        PLAYER_ONE = 1, "Joueur 1"
        PLAYER_TWO = 2, "Joueur 2"

    # Une partie possède deux participants : joueur 1 et joueur 2.
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

    position = models.PositiveSmallIntegerField(
        choices=Position.choices,
    )

    # Nombre de manches remportées. Une victoire vaut 1 point ;
    # une défaite ou une égalité ne rapporte aucun point.
    score = models.PositiveSmallIntegerField(
        default=0,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(26),
        ],
    )

    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position"]

        constraints = [
            # Le même utilisateur ne peut pas rejoindre deux fois la même partie.
            models.UniqueConstraint(
                fields=["game", "user"],
                name="unique_user_per_game",
            ),
            # Chaque position de joueur est unique dans une partie.
            models.UniqueConstraint(
                fields=["game", "position"],
                name="unique_player_position_per_game",
            ),
        ]

    def __str__(self):
        return (
            f"{self.user.username} — "
            f"partie {self.game_id} — "  # type: ignore[attr-defined]
            f"{self.get_position_display()}"  # type: ignore[attr-defined]
        )


class GameCard(models.Model):
    """Carte distribuée dans la pioche d'un joueur pour une partie donnée."""

    class Suit(models.TextChoices):
        # Les enseignes identifient les 52 cartes, mais elles n'ont aucune
        # influence sur la puissance d'une carte.
        HEARTS = "HEARTS", "Cœur"
        DIAMONDS = "DIAMONDS", "Carreau"
        CLUBS = "CLUBS", "Trèfle"
        SPADES = "SPADES", "Pique"

    class Rank(models.IntegerChoices):
        # Les valeurs numériques suivent l'ordre de puissance du jeu :
        # 2 est la plus faible carte et 14 représente l'As.
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

    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="cards",
    )

    owner = models.ForeignKey(
        GamePlayer,
        on_delete=models.CASCADE,
        related_name="cards",
    )

    suit = models.CharField(
        max_length=10,
        choices=Suit.choices,
    )

    rank = models.PositiveSmallIntegerField(
        choices=Rank.choices,
    )

    # Position de la carte dans la pioche du joueur. Le serveur joue toujours
    # la première carte non jouée, donc le joueur ne choisit pas sa carte.
    position = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(26),
        ],
    )

    # Indique que la carte a déjà été jouée. Elle reste enregistrée
    # pour conserver l'historique, mais ne peut plus être utilisée.
    is_played = models.BooleanField(default=False)

    class Meta:
        ordering = ["position"]

        constraints = [
            # Une même partie ne peut contenir qu'un seul exemplaire
            # de chaque combinaison enseigne + valeur.
            models.UniqueConstraint(
                fields=["game", "suit", "rank"],
                name="unique_card_per_game",
            ),
            # La position fixe l'ordre de la pioche de chaque joueur.
            models.UniqueConstraint(
                fields=["owner", "position"],
                name="unique_position_per_player_deck",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_rank_display()} "  # type: ignore[attr-defined]
            f"de {self.get_suit_display()}"  # type: ignore[attr-defined]
        )


class Round(models.Model):
    """Manche de jeu : chaque joueur révèle une carte, puis le serveur compare."""

    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="rounds",
    )

    number = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(26),
        ],
    )

    # Ces champs restent vide tant que le joueur concerné n'a pas
    # retourné sa carte. La manche est complétée en deux actions.
    player_one_card = models.ForeignKey(
        GameCard,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="rounds_as_player_one_card",
    )

    player_two_card = models.ForeignKey(
        GameCard,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="rounds_as_player_two_card",
    )

    # Null signifie soit que la manche n'est pas encore résolue,
    # soit qu'elle s'est terminée par une égalité.
    # is_resolved permet de distinguer les deux situations.
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
            # Une manche ne peut être jouée qu'une seule fois dans une partie.
            models.UniqueConstraint(
                fields=["game", "number"],
                name="unique_round_number_per_game",
            ),
            # Les deux joueurs ne peuvent pas révéler le même objet carte.
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
        """Indique si la manche est résolue par une égalité."""
        return self.is_resolved and self.winner is None

    def __str__(self) -> str:
        return f"Manche {self.number} — partie {self.game_id}"  # type: ignore[attr-defined]

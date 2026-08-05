# Generated manually because makemigrations proposed deleting GameCard.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

SUITS = ["HEARTS", "DIAMONDS", "CLUBS", "SPADES"]
RANKS = range(2, 15)


def migrate_existing_game_cards(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    Profile = apps.get_model("game", "Profile")
    Card = apps.get_model("game", "Card")
    Deck = apps.get_model("game", "Deck")
    DeckCard = apps.get_model("game", "DeckCard")
    Game = apps.get_model("game", "Game")

    for user in User.objects.all():
        Profile.objects.get_or_create(user=user)

    for suit in SUITS:
        for rank in RANKS:
            Card.objects.get_or_create(suit=suit, rank=rank)

    for game in Game.objects.all():
        Deck.objects.get_or_create(game=game)

    cards_by_key = {(card.suit, card.rank): card for card in Card.objects.all()}
    decks_by_game = {
        deck.game_id: deck  # pyright: ignore[reportAttributeAccessIssue]
        for deck in Deck.objects.all()
    }

    for deck_card in DeckCard.objects.all():
        game_id = deck_card.game_id  # pyright: ignore[reportAttributeAccessIssue]
        deck_card.deck = decks_by_game.get(game_id)
        deck_card.card = cards_by_key[(deck_card.suit, deck_card.rank)]
        deck_card.save(update_fields=["deck", "card"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Profile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("games_played", models.PositiveIntegerField(default=0)),
                ("games_won", models.PositiveIntegerField(default=0)),
                ("total_score", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="game_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Card",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "suit",
                    models.CharField(
                        choices=[
                            ("HEARTS", "Coeur"),
                            ("DIAMONDS", "Carreau"),
                            ("CLUBS", "Trefle"),
                            ("SPADES", "Pique"),
                        ],
                        max_length=10,
                    ),
                ),
                (
                    "rank",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (2, "2"),
                            (3, "3"),
                            (4, "4"),
                            (5, "5"),
                            (6, "6"),
                            (7, "7"),
                            (8, "8"),
                            (9, "9"),
                            (10, "10"),
                            (11, "Valet"),
                            (12, "Dame"),
                            (13, "Roi"),
                            (14, "As"),
                        ],
                    ),
                ),
            ],
            options={"ordering": ["suit", "rank"]},
        ),
        migrations.CreateModel(
            name="Deck",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("shuffled_at", models.DateTimeField(blank=True, null=True)),
                (
                    "game",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deck",
                        to="game.game",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="MoveLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("GAME_CREATED", "Partie creee"),
                            ("PLAYER_JOINED", "Joueur arrive"),
                            ("GAME_STARTED", "Partie demarree"),
                            ("CARD_PLAYED", "Carte ajoutee"),
                            ("ROUND_RESOLVED", "Manche resolue"),
                            ("GAME_FINISHED", "Partie terminee"),
                        ],
                        max_length=30,
                    ),
                ),
                ("details", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "game",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="move_logs",
                        to="game.game",
                    ),
                ),
                (
                    "player",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="move_logs",
                        to="game.gameplayer",
                    ),
                ),
                (
                    "round",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="move_logs",
                        to="game.round",
                    ),
                ),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.RemoveConstraint(
            model_name="gamecard",
            name="unique_card_per_game",
        ),
        migrations.RemoveConstraint(
            model_name="gamecard",
            name="unique_position_per_player_deck",
        ),
        migrations.AddField(
            model_name="game",
            name="stats_recorded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RenameModel(
            old_name="GameCard",
            new_name="DeckCard",
        ),
        migrations.AlterModelOptions(
            name="deckcard",
            options={"ordering": ["owner__position", "position"]},
        ),
        migrations.AlterField(
            model_name="deckcard",
            name="owner",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="deck_cards",
                to="game.gameplayer",
            ),
        ),
        migrations.AddField(
            model_name="deckcard",
            name="card",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="deck_cards",
                to="game.card",
            ),
        ),
        migrations.AddField(
            model_name="deckcard",
            name="deck",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="cards",
                to="game.deck",
            ),
        ),
        migrations.AddField(
            model_name="deckcard",
            name="played_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(migrate_existing_game_cards, noop_reverse),
        migrations.AlterField(
            model_name="deckcard",
            name="card",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="deck_cards",
                to="game.card",
            ),
        ),
        migrations.AlterField(
            model_name="deckcard",
            name="deck",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="cards",
                to="game.deck",
            ),
        ),
        migrations.AlterField(
            model_name="round",
            name="player_one_card",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="rounds_as_player_one_card",
                to="game.deckcard",
            ),
        ),
        migrations.AlterField(
            model_name="round",
            name="player_two_card",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="rounds_as_player_two_card",
                to="game.deckcard",
            ),
        ),
        migrations.RemoveField(
            model_name="deckcard",
            name="game",
        ),
        migrations.RemoveField(
            model_name="deckcard",
            name="rank",
        ),
        migrations.RemoveField(
            model_name="deckcard",
            name="suit",
        ),
        migrations.AddConstraint(
            model_name="game",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("current_round__gte", 0),
                    ("current_round__lte", 26),
                ),
                name="game_current_round_between_0_and_26",
            ),
        ),
        migrations.AddConstraint(
            model_name="gameplayer",
            constraint=models.CheckConstraint(
                condition=models.Q(("position__in", [1, 2])),
                name="game_player_position_is_1_or_2",
            ),
        ),
        migrations.AddConstraint(
            model_name="gameplayer",
            constraint=models.CheckConstraint(
                condition=models.Q(("score__gte", 0), ("score__lte", 26)),
                name="game_player_score_between_0_and_26",
            ),
        ),
        migrations.AddConstraint(
            model_name="card",
            constraint=models.UniqueConstraint(
                fields=("suit", "rank"),
                name="unique_standard_card",
            ),
        ),
        migrations.AddConstraint(
            model_name="deckcard",
            constraint=models.UniqueConstraint(
                fields=("deck", "card"),
                name="unique_physical_card_per_deck",
            ),
        ),
        migrations.AddConstraint(
            model_name="deckcard",
            constraint=models.UniqueConstraint(
                fields=("owner", "position"),
                name="unique_position_per_player_deck",
            ),
        ),
        migrations.AddConstraint(
            model_name="deckcard",
            constraint=models.CheckConstraint(
                condition=models.Q(("position__gte", 1), ("position__lte", 26)),
                name="deck_card_position_between_1_and_26",
            ),
        ),
        migrations.AddConstraint(
            model_name="round",
            constraint=models.CheckConstraint(
                condition=models.Q(("number__gte", 1), ("number__lte", 26)),
                name="round_number_between_1_and_26",
            ),
        ),
        migrations.AddIndex(
            model_name="movelog",
            index=models.Index(
                fields=["game", "created_at"],
                name="game_movelo_game_id_90a424_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="movelog",
            index=models.Index(fields=["action"], name="game_movelo_action_6525e7_idx"),
        ),
    ]

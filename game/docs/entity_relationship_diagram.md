
erDiagram
    direction TB

    USER {
        int id PK
        string username
    }

    PROFILE {
        int id PK
        int user_id FK
        int games_played
        int games_won
        int total_score
        datetime created_at
        datetime updated_at
    }

    GAME {
        int id PK
        string status
        int current_round
        int winner_id FK
        datetime created_at
        datetime started_at
        datetime finished_at
        datetime stats_recorded_at
    }

    GAMEPLAYER {
        int id PK
        int game_id FK
        int user_id FK
        int position
        int score
        datetime joined_at
    }

    CARD {
        int id PK
        string suit
        int rank
    }

    DECK {
        int id PK
        int game_id FK
        datetime created_at
        datetime shuffled_at
    }

    DECKCARD {
        int id PK
        int deck_id FK
        int card_id FK
        int owner_id FK
        int position
        boolean is_played
        datetime played_at
    }

    ROUND {
        int id PK
        int game_id FK
        int number
        int player_one_card_id FK
        int player_two_card_id FK
        int winner_id FK
        boolean is_resolved
        datetime created_at
        datetime resolved_at
    }

    MOVELOG {
        int id PK
        int game_id FK
        int player_id FK
        int round_id FK
        string action
        json details
        datetime created_at
    }

    USER ||--o| PROFILE : has
    USER ||--o{ GAMEPLAYER : participates
    GAME ||--o{ GAMEPLAYER : contains
    GAMEPLAYER ||--o{ GAME : wins

    GAME ||--|| DECK : has
    DECK ||--o{ DECKCARD : contains
    CARD ||--o{ DECKCARD : represents
    GAMEPLAYER ||--o{ DECKCARD : owns

    GAME ||--o{ ROUND : has
    DECKCARD ||--o{ ROUND : player_one_card
    DECKCARD ||--o{ ROUND : player_two_card
    GAMEPLAYER ||--o{ ROUND : wins

    GAME ||--o{ MOVELOG : logs
    GAMEPLAYER ||--o{ MOVELOG : actor
    ROUND ||--o{ MOVELOG : references

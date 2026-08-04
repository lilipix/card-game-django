from django.contrib import admin

# Register your models here.
from .models import Game, GameCard, GamePlayer, Round

admin.site.register(Game)
admin.site.register(GamePlayer)
admin.site.register(GameCard)
admin.site.register(Round)

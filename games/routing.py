from django.urls import re_path
from . import consumers 

websocket_urlpatterns = [
    re_path(r'ws/game/(?P<room_code>\w+)/$', consumers.GameConsumer.as_asgi()),
    re_path(r'ws/snake-game/(?P<room_code>\w+)/$', consumers.SnakeGameConsumer.as_asgi()),
    re_path(r'ws/football/(?P<room_code>\w+)/$', consumers.FootballGameConsumer.as_asgi()),
    
]

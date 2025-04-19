import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import GameRoom, PlayerStatus
from django.contrib.auth.models import User
from datetime import datetime
from django.utils import timezone




# consumer.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

class ChessConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.room_group_name = None
        self.room_name = None
        self.players = {}  # Maps channel_name to player color
        self.game_state = {
            'board': [
                ['r', 'n', 'b', 'q', 'k', 'b', 'n', 'r'],
                ['p', 'p', 'p', 'p', 'p', 'p', 'p', 'p'],
                ['', '', '', '', '', '', '', ''],
                ['', '', '', '', '', '', '', ''],
                ['', '', '', '', '', '', '', ''],
                ['', '', '', '', '', '', '', ''],
                ['P', 'P', 'P', 'P', 'P', 'P', 'P', 'P'],
                ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R']
            ],
            'current_player': 'white',
            'move_count': 0
        }

    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_code']
        self.room_group_name = f'chess_{self.room_name}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

        # Assign player color
        if len(self.players) < 2:
            player_color = 'white' if not self.players else 'black'
            self.players[self.channel_name] = player_color
            await self.send(text_data=json.dumps({
                'type': 'player_assignment',
                'color': player_color
            }))
            await self.send_game_state()

    async def disconnect(self, close_code):
        # Leave room group
        if self.channel_name in self.players:
            del self.players[self.channel_name]
        
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # async def receive(self, text_data):
    #     data = json.loads(text_data)
    #     message_type = data.get('type')

    #     if message_type == 'join':
    #         # Already handled in connect, but we'll resend state
    #         await self.send_game_state()
        
    #     elif message_type == 'move':
    #         await self.handle_move(data)
        
    #     elif message_type == 'chat_message':
    #         await self.channel_layer.group_send(
    #             self.room_group_name,
    #             {
    #                 'type': 'chat_message',
    #                 'message': data['message']
    #             }
    #         )

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('type')

        if action == 'move':
            move = data['move']
            board = data['board']
            current_player = data['current_player']  # Client suggests the next player
            player = data['player']

            # Validate the move if needed (optional server-side check)
            next_player = 'black' if current_player == 'white' else 'white'

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chess_move_update',
                    'player': player,
                    'move': move,
                    'board': board,
                    'current_player': next_player,  # Ensure this is the next player
                }
            )

        elif action == 'chat_message':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': data['message']
                }
            )

    async def handle_move(self, data):
        player = data.get('player')
        move = data.get('move')
        board = data.get('board')
        received_current_player = data.get('currentPlayer')

        # Validate it's the correct player's turn
        if player != self.game_state['current_player']:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f"Not {player}'s turn!"
            }))
            return

        # Update game state
        self.game_state['board'] = board
        self.game_state['move_count'] += 1
        # Switch turns
        self.game_state['current_player'] = 'black' if player == 'white' else 'white'

        # Broadcast move to all players
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chess_move_update',
                'move': move,
                'board': board,
                'player': player,
                'currentPlayer': self.game_state['current_player']
            }
        )

    async def send_game_state(self):
        await self.send(text_data=json.dumps({
            'type': 'game_state',
            'board': self.game_state['board'],
            'currentPlayer': self.game_state['current_player']
        }))

    # Handler for group messages
    async def chess_move_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chess_move_update',
            'move': event['move'],
            'board': event['board'],
            'player': event['player'],
            'currentPlayer': event['currentPlayer']
        }))

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message']
        }))



from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import GameRoom, PlayerStatus  # Adjust import based on your app structure
import json

class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_code = self.scope['url_route']['kwargs']['room_code']
        self.user = self.scope["user"]
        self.room_group_name = f"game_{self.room_code}"

        # Get the game room from the database
        self.game_room = await self.get_game_room(self.room_code)

        # Ensure the user is part of the game room
        if not await self.is_user_in_game(self.user, self.game_room):
            await self.close()
            return

        # Join room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        # Accept the WebSocket connection
        await self.accept()

        # Assign player color
        player_color = await self.assign_player_color(self.user, self.game_room)
        if player_color == 'spectator':
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Room is full!',
            }))
            await self.close()
            return

        # Send player assignment
        await self.send(text_data=json.dumps({
            'type': 'player_assignment',
            'color': player_color,
            'player': self.user.username,
        }))

        # Notify all players about the new connection
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'player_join',
                'player': self.user.username,
            }
        )

        # Check if two players are connected to start the game
        current_players = await self.get_player_count(self.game_room)
        if current_players == 2:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'game_start',
                    'message': 'Game started with 2 players!',
                    'current_player': 'white',  # Initial turn
                }
            )

    @database_sync_to_async
    def get_game_room(self, room_code):
        return GameRoom.objects.get(room_code=room_code)

    @database_sync_to_async
    def is_user_in_game(self, user, game_room):
        return user in game_room.players.all()

    @database_sync_to_async
    def assign_player_color(self, user, game_room):
        players = list(game_room.players.all())
        if len(players) > 2:
            return 'spectator'
        if players[0] == user:
            return 'white'
        elif players[1] == user:
            return 'black'
        return 'spectator'

    @database_sync_to_async
    def get_player_count(self, game_room):
        return game_room.players.count()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

   


    async def receive(self, text_data):
            data = json.loads(text_data)
            action = data.get('type')

            if action == 'move':
                move = data['move']
                board = data['board']
                player = data['player']

                # Server determines the next player based on the current player who made the move
                next_player = 'black' if player == 'white' else 'white'

                # Optional: Add server-side move validation here if desired
                # For now, trust the client's board state

                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chess_move_update',
                        'player': player,
                        'move': move,
                        'board': board,
                        'current_player': next_player,  # Server decides this
                    }
                )

            elif action == 'chat_message':
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'message': data['message']
                    }
                )
    async def player_join(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_join',
            'player': event['player'],
        }))

    async def game_start(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_start',
            'message': event['message'],
            'current_player': event['current_player'],
        }))

    async def chess_move_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chess_move_update',
            'player': event['player'],
            'move': event['move'],
            'board': event['board'],
            'current_player': event['current_player'],
        }))

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message']
        }))



#___________start Snake_____________

# class SnakeGameConsumer(AsyncWebsocketConsumer):
#     async def connect(self):
#         self.room_code = self.scope['url_route']['kwargs']['room_code']
#         self.room_group_name = f"snake_game_{self.room_code}"

#         # Initialize snake game data storage if it doesn't exist
#         if not hasattr(self.channel_layer, "snake_game_data"):
#             self.channel_layer.snake_game_data = {}

#         # Add current player to the game room
#         self.channel_layer.snake_game_data[self.channel_name] = [{"x": 100, "y": 100}]  # Default starting position

#         await self.channel_layer.group_add(self.room_group_name, self.channel_name)
#         await self.accept()

#     async def disconnect(self, close_code):
#         # Remove player's snake data on disconnect
#         if self.channel_name in self.channel_layer.snake_game_data:
#             del self.channel_layer.snake_game_data[self.channel_name]

#         await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

#     async def receive(self, text_data):
#         data = json.loads(text_data)

#         if data.get("type") == "snake_update":
#             # Update the player's snake position
#             self.channel_layer.snake_game_data[self.channel_name] = data["snake"]

#             # Broadcast the updated snake game state to all players
#             await self.channel_layer.group_send(
#                 self.room_group_name,
#                 {
#                     "type": "snake_game_update",
#                     "snake_data": self.channel_layer.snake_game_data,
#                 }
#             )

#     async def snake_game_update(self, event):
#         # Broadcast updated snake data to all players in the room
#         await self.send(text_data=json.dumps({
#             "type": "snake_game_update",
#             "snake_data": event["snake_data"],
#         }))




import json
import random
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

class SnakeGameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_code = self.scope['url_route']['kwargs']['room_code']
        self.room_group_name = f"snake_game_{self.room_code}"

        # Initialize game data storage per room
        if not hasattr(self.channel_layer, "game_data"):
            self.channel_layer.game_data = {}
        if self.room_group_name not in self.channel_layer.game_data:
            self.channel_layer.game_data[self.room_group_name] = {
                "snake_data": {},
                "food_data": {}
            }

        # Add player with initial snake and score
        self.channel_layer.game_data[self.room_group_name]["snake_data"][self.channel_name] = {
            "snake": [{"x": 100, "y": 100}],
            "score": 0
        }

        # Spawn initial food
        await self.spawn_food()

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if self.room_group_name in self.channel_layer.game_data:
            if self.channel_name in self.channel_layer.game_data[self.room_group_name]["snake_data"]:
                # Convert disconnected snake to food
                snake = self.channel_layer.game_data[self.room_group_name]["snake_data"][self.channel_name]["snake"]
                for segment in snake:
                    food_id = f"{self.channel_name}_{random.randint(0, 1000000)}"
                    self.channel_layer.game_data[self.room_group_name]["food_data"][food_id] = {
                        "x": segment["x"],
                        "y": segment["y"],
                        "pulse": 1,
                        "grow": True,
                        "color": "orange",
                        "points": 15,
                        "baseSize": 8
                    }
                del self.channel_layer.game_data[self.room_group_name]["snake_data"][self.channel_name]
            # Clean up empty rooms
            if not self.channel_layer.game_data[self.room_group_name]["snake_data"]:
                del self.channel_layer.game_data[self.room_group_name]
            else:
                # Broadcast updated state after disconnection
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "snake_game_update",
                        "snake_data": self.channel_layer.game_data[self.room_group_name]["snake_data"],
                        "food_data": self.channel_layer.game_data[self.room_group_name]["food_data"],
                        "leaderboard": self.compute_leaderboard()
                    }
                )
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    def compute_leaderboard(self):
        game_data = self.channel_layer.game_data[self.room_group_name]
        # Get all players and their scores
        players = [
            {"id": channel, "score": data["score"]}
            for channel, data in game_data["snake_data"].items()
        ]
        # Sort by score in descending order
        players.sort(key=lambda x: x["score"], reverse=True)
        # Top 3 players
        top_3 = players[:3]
        # Compute ranks (1-based)
        ranks = {player["id"]: i + 1 for i, player in enumerate(players)}
        return {
            "top_3": top_3,
            "ranks": ranks
        }

    async def receive(self, text_data):
        data = json.loads(text_data)
        game_data = self.channel_layer.game_data[self.room_group_name]

        if data.get("type") == "snake_update":
            # Update player's snake and score
            game_data["snake_data"][self.channel_name] = {
                "snake": data["snake"],
                "score": data["score"]
            }

            # Check for collisions
            collided_channels = []
            for channel, player_data in game_data["snake_data"].items():
                head = player_data["snake"][0]
                for other_channel, other_player_data in game_data["snake_data"].items():
                    if channel != other_channel:
                        for segment in other_player_data["snake"]:
                            if abs(head["x"] - segment["x"]) < 20 and abs(head["y"] - segment["y"]) < 20:
                                collided_channels.append(channel)
                                break
                if channel in collided_channels:
                    break

            # Handle collisions
            for channel in set(collided_channels):
                snake = game_data["snake_data"][channel]["snake"]
                for segment in snake:
                    food_id = f"{channel}_{len(game_data['food_data'])}"
                    game_data["food_data"][food_id] = {
                        "x": segment["x"],
                        "y": segment["y"],
                        "pulse": 1,
                        "grow": True,
                        "color": "orange",
                        "points": 15,
                        "baseSize": 8
                    }
                game_data["snake_data"][channel] = {
                    "snake": [{"x": random.randint(-1000, 1000), "y": random.randint(-1000, 1000)}],
                    "score": 0
                }

            # Broadcast game state with leaderboard
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "snake_game_update",
                    "snake_data": game_data["snake_data"],
                    "food_data": game_data["food_data"],
                    "leaderboard": self.compute_leaderboard()
                }
            )

        elif data.get("type") == "food_eaten":
            # Remove eaten food
            food_keys = list(game_data["food_data"].keys())
            for index in sorted(data.get("eaten_indices", []), reverse=True):
                if index < len(food_keys):
                    del game_data["food_data"][food_keys[index]]
            # Update player's score
            game_data["snake_data"][self.channel_name]["score"] = data["score"]
            # Spawn new food
            await self.spawn_food(snake_head=data.get("snake_head"))
            # Broadcast updated state with leaderboard
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "snake_game_update",
                    "snake_data": game_data["snake_data"],
                    "food_data": game_data["food_data"],
                    "leaderboard": self.compute_leaderboard()
                }
            )

        elif data.get("type") == "request_food":
            await self.spawn_food(snake_head=data.get("snake_head"))
            # Broadcast updated state with leaderboard
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "snake_game_update",
                    "snake_data": game_data["snake_data"],
                    "food_data": game_data["food_data"],
                    "leaderboard": self.compute_leaderboard()
                }
            )

        elif data.get("type") == "request_initial_state":
            await self.send(text_data=json.dumps({
                "type": "snake_game_update",
                "snake_data": game_data["snake_data"],
                "food_data": game_data["food_data"],
                "leaderboard": self.compute_leaderboard()
            }))

    async def spawn_food(self, snake_head=None):
        game_data = self.channel_layer.game_data[self.room_group_name]
        types = [
            {"color": "red", "points": 30, "size": 8},
            {"color": "yellow", "points": 20, "size": 10},
            {"color": "blue", "points": 10, "size": 14},
        ]
        # Ensure at least 5 foods, up to 10
        while len(game_data["food_data"]) < 10:
            type_data = random.choice(types)
            food_id = f"food_{random.randint(0, 1000000)}"
            if snake_head:
                # Spawn food within 500 units of snake head
                x = snake_head["x"] + random.randint(-500, 500)
                y = snake_head["y"] + random.randint(-500, 500)
            else:
                x = random.randint(-1000, 1000)
                y = random.randint(-1000, 1000)
            game_data["food_data"][food_id] = {
                "x": x,
                "y": y,
                "pulse": 1,
                "grow": True,
                "color": type_data["color"],
                "points": type_data["points"],
                "baseSize": type_data["size"]
            }
        # Remove excess food if more than 10
        while len(game_data["food_data"]) > 10:
            food_keys = list(game_data["food_data"].keys())
            del game_data["food_data"][food_keys[0]]

    async def snake_game_update(self, event):
        await self.send(text_data=json.dumps({
            "type": "snake_game_update",
            "snake_data": event["snake_data"],
            "food_data": event["food_data"],
            "leaderboard": event["leaderboard"]
        }))
#____________snake end_________




#__________Snake____
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from .models import FootballPlayer, FootballRoom, FootballMatchScore

# Game state
game_state = {
    "players": {},  # {player_id: {"x": x, "y": y, "team": "A/B", "score": 0}}
    "ball": {"x": 400, "y": 300},
    "scores": {"teamA": 0, "teamB": 0},
}



import json
from channels.generic.websocket import AsyncWebsocketConsumer

class FootballGameConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game_state = {
            'players': {
                'A_gk': {'x': 50, 'y': 300, 'team': 'A', 'role': 'goalkeeper'},
                'A_1': {'x': 200, 'y': 150, 'team': 'A', 'role': 'field'},
                'A_2': {'x': 200, 'y': 300, 'team': 'A', 'role': 'field'},
                'A_3': {'x': 200, 'y': 450, 'team': 'A', 'role': 'field'},
                'A_4': {'x': 350, 'y': 300, 'team': 'A', 'role': 'field'},
                'B_gk': {'x': 950, 'y': 300, 'team': 'B', 'role': 'goalkeeper'},
                'B_1': {'x': 800, 'y': 150, 'team': 'B', 'role': 'field'},
                'B_2': {'x': 800, 'y': 300, 'team': 'B', 'role': 'field'},
                'B_3': {'x': 800, 'y': 450, 'team': 'B', 'role': 'field'},
                'B_4': {'x': 650, 'y': 300, 'team': 'B', 'role': 'field'}
            },
            'ball': {'x': 500, 'y': 300, 'vx': 0, 'vy': 0},
            'scores': {'A': 0, 'B': 0}
        }
        self.connected_players = {}

    async def connect(self):
        self.room_code = self.scope['url_route']['kwargs']['room_code']
        self.room_group_name = f'football_{self.room_code}'
        
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        
        # Assign player on connect
        team = 'A' if len([p for p in self.connected_players.values() if p['team'] == 'A']) < 5 else 'B'
        available_players = [p for p in self.game_state['players'].keys() 
                            if p.startswith(team) and p not in [cp['player_id'] for cp in self.connected_players.values()]]
        player_id = available_players[0] if available_players else "A_1"  # Default to A_1 if none available
        
        self.connected_players[self.channel_name] = {'player_id': player_id, 'team': team}
        await self.send(json.dumps({
            'type': 'assign_player',
            'player_id': player_id,
            'team': team,
            'game_state': self.game_state
        }))
        print(f"Assigned {player_id} to {team}")

    async def disconnect(self, close_code):
        if self.channel_name in self.connected_players:
            del self.connected_players[self.channel_name]
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        print(f"Received: {data}")

        if data['type'] == 'join':
            # Already handled in connect, but kept for fallback
            if self.channel_name not in self.connected_players:
                team = 'A' if len([p for p in self.connected_players.values() if p['team'] == 'A']) < 5 else 'B'
                available_players = [p for p in self.game_state['players'].keys() 
                                   if p.startswith(team) and p not in [cp['player_id'] for cp in self.connected_players.values()]]
                player_id = available_players[0] if available_players else "A_1"
                
                self.connected_players[self.channel_name] = {'player_id': player_id, 'team': team}
                await self.send(json.dumps({
                    'type': 'assign_player',
                    'player_id': player_id,
                    'team': team,
                    'game_state': self.game_state
                }))
        
        elif data['type'] == 'player_move':
            player_id = data['player_id']
            if player_id in self.game_state['players']:
                self.game_state['players'][player_id]['x'] = data['movement']['x']
                self.game_state['players'][player_id]['y'] = data['movement']['y']
                await self.broadcast_state()
        
        elif data['type'] == 'ball_update':
            self.game_state['ball'] = data['ball']
            await self.broadcast_state()
        
        elif data['type'] == 'score_update':
            self.game_state['scores'] = data['scores']
            await self.broadcast_state()

    async def broadcast_state(self):
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'state_update',
                'game_state': self.game_state
            }
        )

    async def state_update(self, event):
        await self.send(json.dumps({
            'type': 'state_update',
            'game_state': event['game_state']
        }))
        


import json
import random
import logging
from datetime import datetime
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import GameRoom, PlayerStatus
from django.core.exceptions import ObjectDoesNotExist
import asyncio

logger = logging.getLogger(__name__)

# Board configuration (same as client-side)
board_config = {
    "red": {
        "startPosition": 40,
        "path": [40, 41, 42, 43, 44, 30, 15, 0, 1, 2, 3, 4, 5, 20, 35, 50, 51, 52, 53, 54, 68, 82, 96, 95, 94, 93, 92, 106, 120, 135, 150, 151, 152, 153, 154, 139, 124, 109, 108, 107, 106, 105, 104, 119, 134, 149, 148, 147, 146, 145, 144, 143, 142, 141, 140],
        "homePath": [141, 142, 143, 144, 145, 146],
        "safeSpots": [40, 1, 106, 143, 144, 145, 146]
    },
    "blue": {
        "startPosition": 5,
        "path": [5, 20, 35, 50, 51, 52, 53, 54, 68, 82, 96, 95, 94, 93, 92, 106, 120, 135, 150, 151, 152, 153, 154, 139, 124, 109, 108, 107, 106, 105, 104, 119, 134, 149, 148, 147, 146, 145, 144, 143, 142, 141, 140, 125, 110, 95, 80, 65, 50, 51, 52, 53, 54, 55],
        "homePath": [65, 80, 95, 110, 125, 140],
        "safeSpots": [5, 51, 106, 65, 80, 95, 110, 125, 140]
    },
    "green": {
        "startPosition": 105,
        "path": [105, 104, 119, 134, 149, 148, 147, 146, 145, 144, 143, 142, 141, 140, 125, 110, 95, 80, 65, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 44, 29, 14, 13, 12, 11, 10, 25, 40, 41, 42, 43, 44, 59, 74, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98],
        "homePath": [97, 82, 67, 52, 37, 22],
        "safeSpots": [105, 144, 50, 97, 82, 67, 52, 37, 22]
    },
    "yellow": {
        "startPosition": 154,
        "path": [154, 139, 124, 109, 108, 107, 106, 105, 104, 119, 134, 149, 148, 147, 146, 145, 144, 143, 142, 141, 140, 125, 110, 95, 80, 65, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 44, 29, 14, 13, 12, 11, 10, 25, 40, 41, 42, 43, 44, 59, 74, 89, 104],
        "homePath": [89, 88, 87, 86, 85, 84],
        "safeSpots": [154, 144, 50, 10, 89, 88, 87, 86, 85, 84]
    }
}

class LudoGameConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.room_group_name = None
        self.game_id = None
        self.game_state = {
            "players": {},
            "current_turn": None,
            "dice": None,
            "status": "waiting",
            "winner": None,
            "last_move": None
        }
        self.colors = ["red", "blue", "green", "yellow"]

    async def connect(self):
        self.game_id = self.scope['url_route']['kwargs']['game_id']
        self.room_group_name = f"ludo_{self.game_id}"
        self.user = self.scope["user"]

        logger.info(f"User {self.user.username} connecting to room {self.game_id}")
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        try:
            await self.initialize_player()
            await self.send_game_state()
            await self.check_game_start()
        except Exception as e:
            logger.error(f"Error initializing player {self.user.username}: {str(e)}")
            await self.close()

    async def disconnect(self, close_code):
        logger.info(f"User {self.user.username} disconnected from room {self.game_id}")
        if self.user.username in self.game_state["players"]:
            del self.game_state["players"][self.user.username]
            if self.game_state["current_turn"] == self.user.username:
                await self.switch_turn()
            player_count = len(self.game_state["players"])
            if player_count < 2:
                self.game_state["status"] = "waiting"
            await self.broadcast_game_state()
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            action = data.get("type")
            logger.debug(f"Received message from {self.user.username}: {data}")

            if action == "join":
                await self.initialize_player()
                await self.broadcast_game_state()
            elif action == "ready":
                await self.handle_player_ready()
            elif action == "roll_dice":
                await self.handle_dice_roll()
            elif action == "move":
                await self.handle_piece_move(data["piece"], data["new_position"])
            elif action == "chat":
                await self.handle_chat_message(data["message"])
            elif action == "cancel_move":
                await self.handle_cancel_move()
            elif action == "timeout":
                await self.handle_timeout()
        except Exception as e:
            logger.error(f"Error processing message from {self.user.username}: {str(e)}")
            await self.send(text_data=json.dumps({
                "type": "notification",
                "message": f"Error: {str(e)}"
            }))

    async def initialize_player(self):
        room = await self.get_game_room()
        player_status = await self.get_or_create_player_status(room)
        
        if self.user.username not in self.game_state["players"]:
            color = await self.assign_color(room)
            self.game_state["players"][self.user.username] = {
                "color": color,
                "pieces": player_status.current_position or {"piece1": -1, "piece2": -1, "piece3": -1, "piece4": -1},
                "ready": player_status.is_ready
            }
            if not self.game_state["current_turn"] and len(self.game_state["players"]) == 1:
                self.game_state["current_turn"] = self.user.username
            logger.info(f"Initialized player {self.user.username} with color {color}")
            await self.broadcast_game_state()

    async def handle_dice_roll(self):
        if self.game_state["current_turn"] != self.user.username or self.game_state["dice"] is not None:
            logger.warning(f"Invalid dice roll attempt by {self.user.username}")
            return
        
        dice = random.randint(1, 6)
        self.game_state["dice"] = dice
        
        # Check if player has valid moves before sending dice result
        player = self.game_state["players"][self.user.username]
        has_valid_moves = await self.has_valid_moves(player, dice)
        
        if not has_valid_moves:
            logger.info(f"No valid moves for {self.user.username} after rolling {dice}")
            self.game_state["dice"] = None
            await self.switch_turn()
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "dice_result",
                    "value": dice,
                    "has_valid_moves": has_valid_moves
                }
            )
            await self.broadcast_game_state()
            return
        
        # Simulate roll animation delay
        await asyncio.sleep(1.5)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "dice_result",
                "value": dice,
                "has_valid_moves": has_valid_moves
            }
        )
        logger.info(f"User {self.user.username} rolled a {dice}")

    async def handle_piece_move(self, piece, new_position):
        if self.game_state["current_turn"] != self.user.username:
            logger.warning(f"Invalid move attempt by {self.user.username}: not their turn")
            await self.send(text_data=json.dumps({
                "type": "notification",
                "message": "Not your turn!"
            }))
            return
        player = self.game_state["players"].get(self.user.username)
        if not player or player["color"] != piece["color"]:
            logger.warning(f"Invalid move attempt by {self.user.username}: wrong color or player not found")
            await self.send(text_data=json.dumps({
                "type": "notification",
                "message": "Invalid piece!"
            }))
            return

        piece_id = f"piece{piece['id']}"
        current_pos = player["pieces"].get(piece_id, -1)
        dice_value = self.game_state["dice"]
        valid_move = False

        if current_pos == -1 and dice_value == 6:
            if new_position == board_config[piece["color"]]["startPosition"]:
                valid_move = True
        elif current_pos != -1:
            path = board_config[piece["color"]]["path"]
            current_index = path.index(current_pos) if current_pos in path else -1
            if current_index != -1 and current_index + dice_value < len(path):
                if new_position == path[current_index + dice_value]:
                    valid_move = True

        if valid_move:
            captured = None
            for opponent_name, opponent in self.game_state["players"].items():
                if opponent_name != self.user.username:
                    for opp_piece_id, opp_pos in opponent["pieces"].items():
                        if opp_pos == new_position and new_position not in board_config[piece["color"]]["safeSpots"]:
                            captured = {"color": opponent["color"], "id": int(opp_piece_id.replace("piece", "")), "username": opponent_name}
                            break
                    if captured:
                        break

            old_position = player["pieces"][piece_id]
            player["pieces"][piece_id] = new_position
            player_status = await self.get_or_create_player_status(await self.get_game_room())
            player_status.current_position = player["pieces"]
            await database_sync_to_async(player_status.save)()

            move_data = {
                "type": "move",
                "piece": piece,
                "new_position": new_position
            }
            if captured:
                opponent = self.game_state["players"][captured["username"]]
                opponent["pieces"][f"piece{captured['id']}"] = -1
                player_status = await self.get_or_create_player_status(await self.get_game_room())
                player_status.current_position = opponent["pieces"]
                await database_sync_to_async(player_status.save)()
                move_data["captured"] = captured

            self.game_state["last_move"] = {
                "piece": piece,
                "old_position": old_position,
                "new_position": new_position,
                "dice_value": dice_value,
                "captured": captured
            }
            self.game_state["dice"] = None

            await self.channel_layer.group_send(self.room_group_name, move_data)

            if await self.check_win_condition(player, piece["color"]):
                self.game_state["status"] = "finished"
                self.game_state["winner"] = self.user.username
            else:
                # Only keep turn if player rolled a 6 AND has another valid move
                if dice_value == 6 and await self.has_valid_moves(player, 6):
                    logger.info(f"{self.user.username} rolled a 6 and has valid moves, keeping turn")
                    self.game_state["current_turn"] = self.user.username
                else:
                    await self.switch_turn()

            await self.broadcast_game_state()
        else:
            logger.warning(f"Invalid move by {self.user.username}: piece {piece_id} from {current_pos} to {new_position}")
            await self.send(text_data=json.dumps({
                "type": "notification",
                "message": "Invalid move!"
            }))

    async def has_valid_moves(self, player, dice_value):
        color = player["color"]
        path = board_config[color]["path"]
        
        # Check if any piece can be moved out of home
        if dice_value == 6:
            for piece_id, pos in player["pieces"].items():
                if pos == -1:  # Piece is in home
                    return True
        
        # Check if any piece can be moved along the path
        for piece_id, pos in player["pieces"].items():
            if pos == -1:
                continue  # Piece is in home and we already checked for 6
                
            if pos in path:
                current_index = path.index(pos)
                if current_index + dice_value < len(path):
                    return True
        
        return False

    async def handle_chat_message(self, message):
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat",
                "username": self.user.username,
                "message": message,
                "timestamp": datetime.now().isoformat(),
            }
        )

    async def handle_player_ready(self):
        player_status = await self.get_or_create_player_status(await self.get_game_room())
        await self.set_player_ready(player_status)
        self.game_state["players"][self.user.username]["ready"] = True
        await self.check_game_start()
        await self.broadcast_game_state()

    async def handle_cancel_move(self):
        if self.game_state["current_turn"] != self.user.username or not self.game_state.get("last_move"):
            return
        last_move = self.game_state["last_move"]
        player = self.game_state["players"][self.user.username]
        piece_id = f"piece{last_move['piece']['id']}"
        player["pieces"][piece_id] = last_move["old_position"]
        self.game_state["dice"] = last_move["dice_value"]
        if last_move.get("captured"):
            captured_player = self.game_state["players"][last_move["captured"]["username"]]
            captured_piece_id = f"piece{last_move['captured']['id']}"
            captured_player["pieces"][captured_piece_id] = last_move["new_position"]
        self.game_state["last_move"] = None
        player_status = await self.get_or_create_player_status(await self.get_game_room())
        player_status.current_position = player["pieces"]
        await database_sync_to_async(player_status.save)()
        await self.broadcast_game_state()

    async def handle_timeout(self):
        if self.game_state["current_turn"] == self.user.username:
            self.game_state["dice"] = None
            await self.switch_turn()
            await self.broadcast_game_state()
            logger.info(f"Timeout for {self.user.username}, turn switched")

    async def switch_turn(self):
        players = list(self.game_state["players"].keys())
        if not players:
            self.game_state["current_turn"] = None
            return
        current_idx = players.index(self.game_state["current_turn"]) if self.game_state["current_turn"] in players else -1
        next_idx = (current_idx + 1) % len(players)
        self.game_state["current_turn"] = players[next_idx]
        self.game_state["dice"] = None
        logger.info(f"Switched turn to {self.game_state['current_turn']}")
        await self.broadcast_game_state()

    async def check_game_start(self):
        room = await self.get_game_room()
        player_count = await self.get_player_count(room)
        if 2 <= player_count <= 4 and await self.all_players_ready(room):
            self.game_state["status"] = "playing"
            if not self.game_state["current_turn"] or self.game_state["current_turn"] not in self.game_state["players"]:
                self.game_state["current_turn"] = list(self.game_state["players"].keys())[0]
            await self.broadcast_game_state()
            logger.info(f"Game started in room {self.game_id} with {player_count} players")

    async def check_win_condition(self, player, color):
        home_path_end = board_config[color]["homePath"][-1]
        return all(pos == home_path_end for pos in player["pieces"].values())

    @database_sync_to_async
    def get_game_room(self):
        try:
            return GameRoom.objects.get(room_code=self.game_id)
        except GameRoom.DoesNotExist:
            logger.error(f"Game room {self.game_id} not found")
            raise

    @database_sync_to_async
    def get_or_create_player_status(self, room):
        status, created = PlayerStatus.objects.get_or_create(
            user=self.user, game_room=room,
            defaults={
                "current_position": {"piece1": -1, "piece2": -1, "piece3": -1, "piece4": -1},
                "score": 0,
                "is_ready": False,
                "last_active": datetime.now()
            }
        )
        if created:
            logger.info(f"Created PlayerStatus for {self.user.username} in room {room.room_code}")
        return status

    @database_sync_to_async
    def set_player_ready(self, player_status):
        player_status.is_ready = True
        player_status.last_active = datetime.now()
        player_status.save()
        logger.info(f"Player {self.user.username} marked as ready")

    @database_sync_to_async
    def get_player_count(self, room):
        return room.players.count()

    @database_sync_to_async
    def all_players_ready(self, room):
        return all(status.is_ready for status in PlayerStatus.objects.filter(game_room=room))

    @database_sync_to_async
    def assign_color(self, room):
        used_colors = [status.color for status in PlayerStatus.objects.filter(game_room=room)]
        available_colors = [c for c in self.colors if c not in used_colors]
        color = available_colors[0] if available_colors else "red"
        status = PlayerStatus.objects.get(user=self.user, game_room=room)
        status.color = color
        status.last_active = datetime.now()
        status.save()
        logger.info(f"Assigned color {color} to {self.user.username}")
        return color

    async def send_game_state(self):
        await self.send(text_data=json.dumps({
            "type": "game_state",
            "state": self.game_state,
            "username": self.user.username,
        }))

    async def broadcast_game_state(self):
        await self.channel_layer.group_send(
            self.room_group_name,
            {"type": "game_state_update", "game_state": self.game_state}
        )

    async def game_state_update(self, event):
        await self.send(text_data=json.dumps({
            "type": "game_state",
            "state": event["game_state"],
            "username": self.user.username,
        }))

    async def dice_result(self, event):
        await self.send(text_data=json.dumps({
            "type": "dice_result",
            "value": event["value"],
            "has_valid_moves": event["has_valid_moves"]
        }))

    async def move(self, event):
        await self.send(text_data=json.dumps({
            "type": "move",
            "piece": event["piece"],
            "new_position": event["new_position"],
            "captured": event.get("captured")
        }))

    async def chat(self, event):
        await self.send(text_data=json.dumps({
            "type": "chat",
            "username": event["username"],
            "message": event["message"],
            "timestamp": event["timestamp"],
        }))

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import PlayerStatus
import json

class TicTacToeConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_code = self.scope['url_route']['kwargs']['room_code']
        self.user = self.scope["user"]
        self.room_group_name = f"tic_tac_toe_{self.room_code}"

        self.game_room = await self.get_game_room(self.room_code)

        if not await self.is_user_in_game(self.user, self.game_room):
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        player_symbol = await self.assign_player_symbol(self.user, self.game_room)
        if player_symbol == 'spectator':
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Room is full!',
            }))
            await self.close()
            return

        # Update PlayerStatus with symbol
        await self.update_player_status(self.user, self.game_room, player_symbol)

        await self.send(text_data=json.dumps({
            'type': 'player_assignment',
            'symbol': player_symbol,
            'player': self.user.username,
        }))

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'player_join',
                'player': self.user.username,
            }
        )

        current_players = await self.get_player_count(self.game_room)
        if current_players == 2:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'game_start',
                    'message': 'Game started with 2 players!',
                    'current_player': 'X',
                }
            )

    @database_sync_to_async
    def get_game_room(self, room_code):
        return GameRoom.objects.get(room_code=room_code)

    @database_sync_to_async
    def is_user_in_game(self, user, game_room):
        return user in game_room.players.all()

    @database_sync_to_async
    def assign_player_symbol(self, user, game_room):
        players = list(game_room.players.all())
        if len(players) > 2:
            return 'spectator'
        if players[0] == user:
            return 'X'
        elif players[1] == user:
            return 'O'
        return 'spectator'

    @database_sync_to_async
    def update_player_status(self, user, game_room, symbol):
        player_status, created = PlayerStatus.objects.get_or_create(
            user=user,
            game_room=game_room,
            defaults={'score': 0, 'last_active': timezone.now(), 'current_position': {'symbol': symbol}}
        )
        if not created:
            player_status.current_position = {'symbol': symbol}
            player_status.last_active = timezone.now()
            player_status.save()

    @database_sync_to_async
    def get_player_count(self, game_room):
        return game_room.players.count()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        print(f"Received WebSocket message: {text_data}")  # Debug log
        try:
            data = json.loads(text_data)
            action = data.get('type')

            if action == 'join':
                # Handle join message (no action needed since connect handles it)
                pass

            elif action == 'move':
                if 'move' not in data or 'board' not in data or 'player' not in data:
                    print(f"Invalid move message: {data}")
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'Invalid move data'
                    }))
                    return
                move = data['move']
                board = data['board']
                player = data['player']
                next_player = 'O' if player == 'X' else 'X'

                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'move',
                        'player': player,
                        'move': move,
                        'board': board,
                        'current_player': next_player,
                    }
                )

            elif action == 'timeout':
                if 'player' not in data or 'next_player' not in data:
                    print(f"Invalid timeout message: {data}")
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'Invalid timeout data'
                    }))
                    return
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'timeout',
                        'player': data['player'],
                        'next_player': data['next_player'],
                    }
                )

            elif action == 'chat_message':
                if 'message' not in data:
                    print(f"Invalid chat message: {data}")
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'Invalid chat message'
                    }))
                    return
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'message': data['message']
                    }
                )

            else:
                print(f"Unknown action: {action}")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': f'Unknown action: {action}'
                }))

        except json.JSONDecodeError:
            print(f"Invalid JSON: {text_data}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid message format'
            }))

    async def player_join(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_join',
            'player': event['player'],
        }))

    async def game_start(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_start',
            'message': event['message'],
            'current_player': event['current_player'],
        }))

    async def move(self, event):
        await self.send(text_data=json.dumps({
            'type': 'move',
            'player': event['player'],
            'move': event['move'],
            'board': event['board'],
            'current_player': event['current_player'],
        }))

    async def timeout(self, event):
        await self.send(text_data=json.dumps({
            'type': 'timeout',
            'player': event['player'],
            'next_player': event['next_player'],
        }))

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message']
        }))        
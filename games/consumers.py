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
        

#_________start Ludo_________





#_____end ludo        

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
        #print(f"Received WebSocket message: {text_data}")  # Debug log
        try:
            data = json.loads(text_data)
            action = data.get('type')

            if action == 'join':
                # Handle join message (no action needed since connect handles it)
                pass

            elif action == 'move':
                if 'move' not in data or 'board' not in data or 'player' not in data:
                    #print(f"Invalid move message: {data}")
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
                    #print(f"Invalid timeout message: {data}")
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
                    #print(f"Invalid chat message: {data}")
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
                #print(f"Unknown action: {action}")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': f'Unknown action: {action}'
                }))

        except json.JSONDecodeError:
            #print(f"Invalid JSON: {text_data}")
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




#___________start Ludo___________


import json
import random
import logging
from datetime import timedelta
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import GameRoom, PlayerStatus
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth import get_user_model
from django.utils import timezone

logger = logging.getLogger(__name__)

class LudoGameConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.room_group_name = None
        self.game_id = None
        self.colors = ["red", "blue", "green", "yellow"]

    async def connect(self):
        self.game_id = self.scope['url_route']['kwargs']['game_id']
        self.room_group_name = f"ludo_{self.game_id}"
        self.user = self.scope["user"]

        logger.info(f"User {self.user.username} connecting to room {self.game_id}")
        self.game_room = await self.get_game_room()

        if not await self.is_user_in_game(self.user, self.game_room):
            await self.send(text_data=json.dumps({
                'type': 'notification',
                'message': 'You are not part of this game room.'
            }))
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        player_color = await self.assign_player_color(self.user, self.game_room)
        if player_color == 'spectator':
            await self.send(text_data=json.dumps({
                'type': 'notification',
                'message': 'Room is full! You are a spectator.'
            }))
        else:
            # Notify the joining player of their assignment
            await self.send(text_data=json.dumps({
                'type': 'player_assignment',
                'color': player_color,
                'player': self.user.username
            }))
            # Broadcast updated player list to all clients
            await self.broadcast_player_list()

        current_players = await self.get_player_count(self.game_room)
        if current_players >= 2:
            # Broadcast game start with full player list
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'game_start',
                    'message': f'Game started with {current_players} players!',
                    'current_player': (await self.get_first_player()).username,
                    'players': await self.get_all_players_data()
                }
            )

    async def disconnect(self, close_code):
        logger.info(f"User {self.user.username} disconnected from room {self.game_id}")
        if hasattr(self, 'game_room'):
            player_status = await self.get_or_create_player_status(self.game_room)
            await self.remove_player_status(player_status)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'player_leave',
                    'player': self.user.username
                }
            )
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            action = data.get('type')
            logger.debug(f"Received message from {self.user.username}: {data}")

            if action == 'roll_dice':
                if await self.is_player_active(self.user.username):
                    dice = random.randint(1, 6)
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'dice_result',
                            'player': self.user.username,
                            'value': dice
                        }
                    )
                else:
                    await self.send(text_data=json.dumps({
                        'type': 'notification',
                        'message': 'Not your turn or you are inactive.'
                    }))
            elif action == 'move':
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'move',
                        'player': self.user.username,
                        'piece': data['piece'],
                        'new_position': data['new_position'],
                        'captured': data.get('captured')
                    }
                )
            elif action == 'chat_message':
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'player': self.user.username,
                        'message': data['message'],
                        'timestamp': timezone.now().isoformat()
                    }
                )
            elif action == 'switch_turn':
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'switch_turn',
                        'next_player': data['next_player']
                    }
                )
            else:
                await self.send(text_data=json.dumps({
                    'type': 'notification',
                    'message': f'Unknown action: {action}'
                }))
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from {self.user.username}: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'notification',
                'message': 'Invalid message format'
            }))
        except Exception as e:
            logger.error(f"Error processing message from {self.user.username}: {str(e)}", exc_info=True)
            await self.send(text_data=json.dumps({
                'type': 'notification',
                'message': f'Error: {str(e)}'
            }))

    @database_sync_to_async
    def get_game_room(self):
        try:
            return GameRoom.objects.get(room_code=self.game_id)
        except GameRoom.DoesNotExist:
            logger.error(f"Game room {self.game_id} not found")
            raise

    @database_sync_to_async
    def is_user_in_game(self, user, game_room):
        return user in game_room.players.all()

    @database_sync_to_async
    def get_player_count(self, game_room):
        return game_room.players.count()

    @database_sync_to_async
    def get_first_player(self):
        return self.game_room.players.first()

    @database_sync_to_async
    def assign_player_color(self, user, game_room):
        from django.db import transaction
        with transaction.atomic():
            used_colors = PlayerStatus.objects.filter(game_room=game_room).exclude(user=user).values_list('color', flat=True)
            available_colors = [c for c in self.colors if c not in used_colors]
            if not available_colors:
                return 'spectator'
            color = available_colors[0]
            status, created = PlayerStatus.objects.get_or_create(
                user=user, game_room=game_room,
                defaults={
                    'color': color,
                    'current_position': {"piece1": -1, "piece2": -1, "piece3": -1, "piece4": -1},
                    'score': 0,
                    'is_ready': False,
                    'last_active': timezone.now()
                }
            )
            if not created and status.color:
                return status.color
            status.color = color
            status.last_active = timezone.now()
            status.save()
            logger.info(f"Assigned color {color} to {user.username}")
            return color
        
    @database_sync_to_async
    def get_all_players_data(self):
        """Retrieve the list of all players with their colors and statuses."""
        player_statuses = PlayerStatus.objects.filter(game_room=self.game_room).select_related('user')
        return [
            {
                'username': status.user.username,
                'color': status.color,
                'active': status.last_active >= timezone.now() - timedelta(minutes=5)
            }
            for status in player_statuses
        ]    
    
    async def broadcast_player_list(self):
        """Broadcast the current player list to all clients."""
        players_data = await self.get_all_players_data()
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'player_list_update',
                'players': players_data
            }
        )

    @database_sync_to_async
    def get_or_create_player_status(self, game_room, username=None):
        User = get_user_model()
        user = self.user if not username else User.objects.get(username=username)
        status, created = PlayerStatus.objects.get_or_create(
            user=user, game_room=game_room,
            defaults={
                'current_position': {"piece1": -1, "piece2": -1, "piece3": -1, "piece4": -1},
                'score': 0,
                'is_ready': False,
                'last_active': timezone.now()
            }
        )
        if created:
            logger.info(f"Created PlayerStatus for {user.username} in room {game_room.room_code}")
        return status

    @database_sync_to_async
    def remove_player_status(self, player_status):
        player_status.delete()
        logger.info(f"Removed PlayerStatus for {self.user.username}")

    @database_sync_to_async
    def is_player_active(self, username):
        try:
            player_status = PlayerStatus.objects.get(user__username=username, game_room__room_code=self.game_id)
            return player_status.last_active >= timezone.now() - timedelta(minutes=5)
        except ObjectDoesNotExist:
            return False

    async def player_join(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_join',
            'player': event['player'],
            'color': event['color']
        }))

    async def player_leave(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_leave',
            'player': event['player']
        }))

    async def game_start(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_start',
            'message': event['message'],
            'current_player': event['current_player']
        }))

    async def dice_result(self, event):
        await self.send(text_data=json.dumps({
            'type': 'dice_result',
            'player': event['player'],
            'value': event['value']
        }))

    async def move(self, event):
        await self.send(text_data=json.dumps({
            'type': 'move',
            'player': event['player'],
            'piece': event['piece'],
            'new_position': event['new_position'],
            'captured': event.get('captured')
        }))

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'player': event['player'],
            'message': event['message'],
            'timestamp': event['timestamp']
        }))

    async def switch_turn(self, event):
        await self.send(text_data=json.dumps({
            'type': 'switch_turn',
            'next_player': event['next_player']
        }))

    async def notification(self, event):
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'message': event['message']
        }))

    async def player_list_update(self, event):
        """Handle player list update message."""
        await self.send(text_data=json.dumps({
            'type': 'player_list_update',
            'players': event['players']
        }))    

    async def game_start(self, event):
        """Handle game start message with player list."""
        await self.send(text_data=json.dumps({
            'type': 'game_start',
            'message': event['message'],
            'current_player': event['current_player'],
            'players': event['players']
        }))    


import json
import random
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from datetime import timedelta

class ZombsRoyaleConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_code = self.scope['url_route']['kwargs']['room_code']
        self.room_group_name = f"zombsroyale_{self.room_code}"

        # Initialize game data storage per room
        if not hasattr(self.channel_layer, "game_data"):
            self.channel_layer.game_data = {}
        if self.room_group_name not in self.channel_layer.game_data:
            self.channel_layer.game_data[self.room_group_name] = {
                "players": {},
                "bullets": {},
                "items": {},
                "zone": {
                    "center": {"x": 0, "z": 0},
                    "radius": 1000,
                    "next_shrink_time": (timezone.now() + timedelta(seconds=30)).timestamp(),
                    "shrink_duration": 10
                }
            }

        # Add player with initial position and stats
        self.channel_layer.game_data[self.room_group_name]["players"][self.channel_name] = {
            "position": {"x": random.uniform(-500, 500), "y": 10, "z": random.uniform(-500, 500)},
            "rotation": 0,
            "health": 100,
            "score": 0,
            "weapon": "pistol",
            "ammo": 30,
            "alive": True
        }

        # Spawn initial items
        await self.spawn_items()

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if self.room_group_name in self.channel_layer.game_data:
            if self.channel_name in self.channel_layer.game_data[self.room_group_name]["players"]:
                del self.channel_layer.game_data[self.room_group_name]["players"][self.channel_name]
            # Clean up empty rooms
            if not self.channel_layer.game_data[self.room_group_name]["players"]:
                del self.channel_layer.game_data[self.room_group_name]
            else:
                # Broadcast updated state after disconnection
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "game_update",
                        "players": self.channel_layer.game_data[self.room_group_name]["players"],
                        "bullets": self.channel_layer.game_data[self.room_group_name]["bullets"],
                        "items": self.channel_layer.game_data[self.room_group_name]["items"],
                        "zone": self.channel_layer.game_data[self.room_group_name]["zone"],
                        "leaderboard": self.compute_leaderboard()
                    }
                )
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    def compute_leaderboard(self):
        game_data = self.channel_layer.game_data[self.room_group_name]
        players = [
            {"id": channel, "score": data["score"]}
            for channel, data in game_data["players"].items() if data["alive"]
        ]
        players.sort(key=lambda x: x["score"], reverse=True)
        top_5 = players[:5]
        ranks = {player["id"]: i + 1 for i, player in enumerate(players)}
        return {
            "top_5": top_5,
            "ranks": ranks
        }

    async def receive(self, text_data):
        data = json.loads(text_data)
        game_data = self.channel_layer.game_data[self.room_group_name]

        if data.get("type") == "player_update":
            if self.channel_name in game_data["players"] and game_data["players"][self.channel_name]["alive"]:
                game_data["players"][self.channel_name].update({
                    "position": data["position"],
                    "rotation": data["rotation"],
                    "score": data.get("score", game_data["players"][self.channel_name]["score"]),
                    "health": data.get("health", game_data["players"][self.channel_name]["health"]),
                    "ammo": data.get("ammo", game_data["players"][self.channel_name]["ammo"]),
                    "alive": data.get("alive", True)
                })

        elif data.get("type") == "shoot":
            bullet_id = f"bullet_{random.randint(0, 1000000)}"
            game_data["bullets"][bullet_id] = {
                "position": data["position"],
                "direction": data["direction"],
                "speed": 50,
                "damage": 20,
                "shooter": self.channel_name,
                "time": timezone.now().timestamp()
            }
            game_data["players"][self.channel_name]["ammo"] -= 1

        elif data.get("type") == "item_pickup":
            item_id = data.get("item_id")
            if item_id in game_data["items"]:
                item = game_data["items"][item_id]
                if item["type"] == "health":
                    game_data["players"][self.channel_name]["health"] = min(
                        100, game_data["players"][self.channel_name]["health"] + 50
                    )
                elif item["type"] == "ammo":
                    game_data["players"][self.channel_name]["ammo"] += 30
                del game_data["items"][item_id]
                await self.spawn_items()

        # Update zone
        current_time = timezone.now().timestamp()
        zone = game_data["zone"]
        if current_time >= zone["next_shrink_time"]:
            zone["radius"] = max(100, zone["radius"] * 0.8)
            zone["next_shrink_time"] = (timezone.now() + timedelta(seconds=30)).timestamp()

        # Check for bullet collisions
        bullets_to_remove = []
        for bullet_id, bullet in list(game_data["bullets"].items()):
            if current_time - bullet["time"] > 5:  # Remove bullets after 5 seconds
                bullets_to_remove.append(bullet_id)
                continue
            for channel, player in game_data["players"].items():
                if channel != bullet["shooter"] and player["alive"]:
                    dx = player["position"]["x"] - bullet["position"]["x"]
                    dz = player["position"]["z"] - bullet["position"]["z"]
                    if (dx ** 2 + dz ** 2) ** 0.5 < 10:
                        player["health"] = max(0, player["health"] - bullet["damage"])
                        if player["health"] <= 0:
                            player["alive"] = False
                            game_data["players"][bullet["shooter"]]["score"] += 100
                        bullets_to_remove.append(bullet_id)
                        break

        for bullet_id in bullets_to_remove:
            if bullet_id in game_data["bullets"]:
                del game_data["bullets"][bullet_id]

        # Broadcast game state
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "game_update",
                "players": game_data["players"],
                "bullets": game_data["bullets"],
                "items": game_data["items"],
                "zone": game_data["zone"],
                "leaderboard": self.compute_leaderboard()
            }
        )

    async def spawn_items(self):
        game_data = self.channel_layer.game_data[self.room_group_name]
        item_types = [
            {"type": "health", "color": "red", "size": 5},
            {"type": "ammo", "color": "yellow", "size": 5}
        ]
        while len(game_data["items"]) < 20:
            item_type = random.choice(item_types)
            item_id = f"item_{random.randint(0, 1000000)}"
            game_data["items"][item_id] = {
                "position": {
                    "x": random.uniform(-800, 800),
                    "y": 5,
                    "z": random.uniform(-800, 800)
                },
                "type": item_type["type"],
                "color": item_type["color"],
                "size": item_type["size"]
            }

    async def game_update(self, event):
        await self.send(text_data=json.dumps({
            "type": "game_update",
            "players": event["players"],
            "bullets": event["bullets"],
            "items": event["items"],
            "zone": event["zone"],
            "leaderboard": event["leaderboard"]
        }))        
from django.shortcuts import render, redirect
from django.http import JsonResponse
from .models import Game, GameRoom, PlayerStatus
from django.contrib.auth.models import User
import uuid
# Add these imports to your existing views.py file
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
import json
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseNotFound
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count
from .models import Game, GameRoom, PlayerStatus
from django.contrib.auth.models import User
import uuid
import requests
from datetime import timedelta
import json



from django.shortcuts import render
from django.http import JsonResponse
from .models import Game, GameRoom
import requests

# PlayCanvas API Details
PLAYCANVAS_API_KEY = "t9qRgISU2NQc2XmzzkvVCh6fh3maG4pP"
PLAYCANVAS_API_URL = "https://playcanvas.com/api/projects"

def fetch_playcanvas_games():
    headers = {"Authorization": f"Bearer {PLAYCANVAS_API_KEY}"}
    response = requests.get(PLAYCANVAS_API_URL, headers=headers)

    if response.status_code == 200:
        games = response.json()
        free_games = [game for game in games if game.get("isPublic", False)]  # Filtering free games
        return free_games  
    return []

def home(request):
    games = Game.objects.filter(is_active=True)
    for game in games:
        game.rooms = GameRoom.objects.filter(game=game, is_active=True).count()

    #playcanvas_games = fetch_playcanvas_games()  # ✅ Now this works without an error

    #return render(request, 'games/home.html', {'games': games, 'playcanvas_games': playcanvas_games})
    return render(request, 'games/home.html', {'games': games})

# def home(request):
#     games = Game.objects.filter(is_active=True)
#     for game in games:
#         # Get the count of active rooms for each game
#         game.rooms = GameRoom.objects.filter(game=game, is_active=True).count()

#     return render(request, 'games/home.html', {'games': games})

# from django.views.decorators.csrf import csrf_exempt

# @csrf_exempt
# def game_room_views(request, game_id):
#     game = Game.objects.get(game_id=game_id)
    
#     if request.method == 'POST':
#         action = request.POST.get('action')
        
#         if action == 'create':
#             room_type = request.POST.get('room_type', 'public')  # Default to 'public'
            
#             # Create a new room with the selected visibility type
#             room = GameRoom.objects.create(
#                 game=game,
#                 created_by=request.user,
#                 room_code=str(uuid.uuid4())[:8].upper(),  # Ensure the room code is uppercase
#                 is_private=(room_type == 'private')
#             )
#             room.players.add(request.user)  # Add the host as a player
#             room.save()
            
#             # Return JSON response with room code
#             return JsonResponse({'room_code': room.room_code})
        
#         elif action == 'join':
#             room_code = request.POST.get('room_code', '').strip().upper()  # Normalize to uppercase
#             try:
#                 room = GameRoom.objects.get(room_code=room_code, game=game)
#                 room.players.add(request.user)  # Add user to the room
#                 room.save()
#                 return JsonResponse({'room_code': room.room_code, 'game_id': game_id})
#             except GameRoom.DoesNotExist:
#                 return JsonResponse({'error': 'Invalid room code or room does not exist'}, status=400)
    
#     return render(request, 'games/game_room.html', {'game': game})



@login_required(login_url='login')
@csrf_exempt
# New view to check if game is starting
def check_game_starting(request, room_code):
    try:
        game_room = GameRoom.objects.get(room_code=room_code)
        
        if game_room.is_starting:
            # Calculate remaining countdown time
            if game_room.start_time:
                now = timezone.now()
                if now < game_room.start_time:
                    seconds_left = (game_room.start_time - now).total_seconds()
                    return JsonResponse({
                        'is_starting': True,
                        'countdown_from': int(seconds_left)
                    })
            
            return JsonResponse({'is_starting': True, 'countdown_from': 5})
        else:
            return JsonResponse({'is_starting': False})
    except GameRoom.DoesNotExist:
        return JsonResponse({'is_starting': False, 'error': 'Room not found'})

# New view to start the countdown
@login_required(login_url='login')
@csrf_exempt
def start_game_countdown(request, room_code, game_id):
    if request.method == 'POST':
        try:
            game_room = GameRoom.objects.get(room_code=room_code)
            
            # Set the game to starting status
            game_room.is_starting = True
            game_room.start_time = timezone.now() + timedelta(seconds=5)  # 5 second countdown
            game_room.save()
            
            return JsonResponse({'status': 'countdown_started'})
        except GameRoom.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Room not found'}, status=404)
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)




from django.utils.timezone import now, timedelta

from django.utils.timezone import now, timedelta
from django.db.models import Count
import uuid
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from .models import Game, GameRoom

@csrf_exempt
@login_required(login_url='login')
def game_room_views(request, game_id):
    try:
        game = Game.objects.get(game_id=game_id)
    except Game.DoesNotExist:
        return render(request, 'games/game_room.html', {'game': None, 'error': 'Game not found'})

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'join_auto':
            if game.slug in ["chess", "tic-tac-toe"]:
                # Find an available room with one player
                room = GameRoom.objects.filter(game=game, is_active=True, is_private=False).annotate(
                    player_count=Count('players')
                ).filter(player_count=1).first()

                if room:
                    room.players.add(request.user)
                    room.is_started = True  # Start game when both players join
                    room.save()
                else:
                    # Create a new room if no available room exists
                    room = GameRoom.objects.create(
                        game=game,
                        created_by=request.user,
                        room_code=str(uuid.uuid4())[:8].upper(),
                        is_private=False
                    )
                    room.players.add(request.user)
                    room.save()

                return JsonResponse({'room_code': room.room_code, 'game_id': game_id})
                
            elif game.slug == "snake":
                activity_threshold = timezone.now() - timedelta(minutes=5)

                # Clean up inactive rooms
                GameRoom.objects.filter(
                    is_active=True,
                    is_private=False,
                    playerstatus__last_active__lt=activity_threshold
                ).update(is_active=False)

                # Find an available room with at least one active player
                room = GameRoom.objects.filter(
                    game=game,
                    is_active=True,
                    is_private=False
                ).annotate(
                    player_count=Count('players')
                ).filter(
                    player_count__lt=99,
                    playerstatus__last_active__gte=activity_threshold
                ).first()

                if not room:
                    room = GameRoom.objects.create(
                        game=game,
                        created_by=request.user,
                        room_code=str(uuid.uuid4())[:8].upper(),
                        is_private=False
                    )

                room.players.add(request.user)

                player_status, created = PlayerStatus.objects.get_or_create(
                    user=request.user,
                    game_room=room,
                    defaults={
                        'score': 0,
                        'last_active': timezone.now()
                    }
                )
                if not created:
                    player_status.last_active = timezone.now()
                    player_status.save()

                room.save()

                return JsonResponse({
                    'room_code': room.room_code,
                    'game_id': game_id
                })
            elif game.slug == "ludo":
                # Find an available room with less than 4 players
                room = GameRoom.objects.filter(game=game, is_active=True, is_private=False).annotate(
                    player_count=Count('players')
                ).filter(player_count__lt=4).first()

                if room:
                    room.players.add(request.user)
                    # Check if game can start (2 to 4 players and all ready)
                    player_statuses = PlayerStatus.objects.filter(game_room=room)
                    if 2 <= room.players.count() <= 4 and all(status.is_ready for status in player_statuses):
                        room.is_started = True
                        room.is_starting = True
                        room.start_time = timezone.now() + timedelta(seconds=5)
                    room.save()
                else:
                    # Create a new room
                    room = GameRoom.objects.create(
                        game=game,
                        created_by=request.user,
                        room_code=str(uuid.uuid4())[:8].upper(),
                        is_private=False
                    )
                    room.players.add(request.user)
                    room.save()

                return JsonResponse({'room_code': room.room_code, 'game_id': game_id})
            

            if game.slug == "zombsroyale":
                activity_threshold = timezone.now() - timedelta(minutes=5)
                GameRoom.objects.filter(
                    is_active=True,
                    is_private=False,
                    playerstatus__last_active__lt=activity_threshold
                ).update(is_active=False)

                room = GameRoom.objects.filter(
                    game=game,
                    is_active=True,
                    is_private=False
                ).annotate(
                    player_count=Count('players')
                ).filter(
                    player_count__lt=50,
                    playerstatus__last_active__gte=activity_threshold
                ).first()

                if not room:
                    room = GameRoom.objects.create(
                        game=game,
                        created_by=request.user,
                        room_code=str(uuid.uuid4())[:8].upper(),
                        is_private=False
                    )

                room.players.add(request.user)
                player_status, created = PlayerStatus.objects.get_or_create(
                    user=request.user,
                    game_room=room,
                    defaults={
                        'score': 0,
                        'last_active': timezone.now()
                    }
                )
                if not created:
                    player_status.last_active = timezone.now()
                    player_status.save()

                room.save()
                return JsonResponse({
                    'room_code': room.room_code,
                    'game_id': game_id
                })
            # ... (other game types remain unchanged)
            

        elif action == 'create_private_room':
            room = GameRoom.objects.create(
                game=game,
                created_by=request.user,
                room_code=str(uuid.uuid4())[:8].upper(),
                is_private=True
            )
            room.players.add(request.user)

            player_status, created = PlayerStatus.objects.get_or_create(
                user=request.user,
                game_room=room,
                defaults={
                    'score': 0,
                    'last_active': timezone.now()
                }
            )
            if not created:
                player_status.last_active = timezone.now()
                player_status.save()

            room.save()

            return JsonResponse({'room_code': room.room_code, 'game_id': game_id, 'private': True})

        elif action == 'join':
            room_code = request.POST.get('room_code', '').strip().upper()
            try:
                room = GameRoom.objects.get(
                    room_code=room_code,
                    game=game,
                    is_active=True
                )
                room.players.add(request.user)

                player_status, created = PlayerStatus.objects.get_or_create(
                    user=request.user,
                    game_room=room,
                    defaults={
                        'score': 0,
                        'last_active': timezone.now()
                    }
                )
                if not created:
                    player_status.last_active = timezone.now()
                    player_status.save()

                room.save()
                return JsonResponse({
                    'room_code': room.room_code,
                    'game_id': game_id
                })
            except GameRoom.DoesNotExist:
                return JsonResponse({
                    'error': 'Invalid room code or room does not exist'
                }, status=400)

    activity_threshold = timezone.now() - timedelta(minutes=5)
    public_rooms = GameRoom.objects.filter(
        game=game,
        is_active=True,
        is_private=False,
        playerstatus__last_active__gte=activity_threshold
    )

    return render(request, 'games/game_room.html', {
        'game': game,
        'public_rooms': public_rooms
    })

@login_required(login_url='login')
@csrf_exempt
def game_lobby(request, room_code, game_id):
    try:
        game_room = GameRoom.objects.get(room_code=room_code)
        
        if game_room.game.game_id != game_id:
            return redirect('home')
        
        player_status, created = PlayerStatus.objects.get_or_create(
            user=request.user,
            game_room=game_room,
            defaults={
                'score': 0,
                'last_active': timezone.now()
            }
        )
        if not created:
            player_status.last_active = timezone.now()
            player_status.save()

        players = game_room.players.all()
        
        if request.method == 'POST':
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                game_room.is_starting = True
                game_room.start_time = timezone.now() + timedelta(seconds=5)
                game_room.save()
                return JsonResponse({
                    'status': 'countdown_started',
                    'redirect': reverse('start_game', kwargs={'room_code': room_code, 'game_id': game_id})
                })
            else:
                game_room.is_starting = True
                game_room.start_time = timezone.now() + timedelta(seconds=5)
                game_room.save()
                return redirect('game_lobby', room_code=room_code, game_id=game_id)
        
        countdown_in_progress = False
        seconds_left = 0
        
        if game_room.is_starting and game_room.start_time:
            now = timezone.now()
            if now < game_room.start_time:
                countdown_in_progress = True
                seconds_left = int((game_room.start_time - now).total_seconds())
            elif now >= game_room.start_time:
                return redirect('start_game', room_code=room_code, game_id=game_id)
        
        return render(request, 'games/game_lobby.html', {
            'game_room': game_room,
            'players': players,
            'countdown_in_progress': countdown_in_progress,
            'seconds_left': seconds_left
        })
        
    except GameRoom.DoesNotExist:
        return HttpResponseNotFound("Game room not found.")

# games/views.py
from django.http import HttpResponseNotFound
from django.shortcuts import render, redirect
from django.urls import reverse
from .models import Game, GameRoom, PlayerStatus


@login_required(login_url='login')
@csrf_exempt
def start_game(request, room_code, game_id):
    try:
        game_room = GameRoom.objects.get(room_code=room_code)
        game = Game.objects.get(game_id=game_id)
        
        if game_room.game.game_id != game_id:
            return redirect('game_lobby', room_code=room_code, game_id=game_id)
        if game.slug == "chess":
            return render(request, 'games/chess.html', {'game_room': game_room})
        elif game.slug == "Agar.io":
            return render(request, 'games/agar.html', {'game_room': game_room})
        elif game.slug == "football":
            return render(request, 'games/football.html', {'game_room': game_room})
        elif game.slug == "snake":
            players_with_scores = []
            for player in game_room.players.all():
                # Get the player's status and score from the PlayerStatus model
                player_status = PlayerStatus.objects.filter(user=player, game_room=game_room).first()
                players_with_scores.append({
                    'username': player.username,
                    'score': player_status.score if player_status else 0,  # Default score to 0 if no status found
                })
            return render(request, 'games/snake.html', {'game_room': game_room, 'players_with_scores': players_with_scores})
        
        elif game.slug == "ludo":
            players_with_positions = []
            for player in game_room.players.all():
                player_status, created = PlayerStatus.objects.get_or_create(
                    user=player,
                    game_room=game_room,
                    defaults={
                        'score': 0,
                        'current_position': {"piece1": -1, "piece2": -1, "piece3": -1, "piece4": -1}
                    }
                )
                players_with_positions.append({
                    'username': player.username,
                    'positions': player_status.current_position,
                })
            return render(request, 'games/ludo.html', {
                'game_room': game_room,
                'players_with_positions': players_with_positions
            })
        elif game.slug == "tic-tac-toe":
            players = []
            for player in game_room.players.all():
                player_status = PlayerStatus.objects.filter(user=player, game_room=game_room).first()
                players.append({
                    'username': player.username,
                    'symbol': player_status.current_position.get('symbol', '') if player_status else ''
                })
            return render(request, 'games/tic_tac_toe.html', {
                'game_room': game_room,
                'players': players
            })
        
        elif game.slug == "zombsroyale":
            players_with_scores = []
            for player in game_room.players.all():
                player_status = PlayerStatus.objects.filter(user=player, game_room=game_room).first()
                players_with_scores.append({
                    'username': player.username,
                    'score': player_status.score if player_status else 0,
                })
            return render(request, 'games/zombsroyale.html', {
                'game_room': game_room,
                'players_with_scores': players_with_scores
            })
        # Add other game cases (chess, snake, etc.) as needed
        else:
            return HttpResponseNotFound("Game not found.")
    except GameRoom.DoesNotExist:
        return HttpResponseNotFound("Game room not found.")
    except Game.DoesNotExist:
        return HttpResponseNotFound("Game not found.")

from django.shortcuts import render
from .models import GameRoom

@login_required(login_url='login')
@csrf_exempt
def chess(request, room_code):
    try:
        # Fetch the game room by the room code
        game_room = GameRoom.objects.get(room_code=room_code)
        
        # Check if the game room is active
        if not game_room.is_active:
            return redirect('game_lobby', room_code=room_code, game_id=game_room.game.game_id)
        
        return render(request, 'games/chess.html', {'game_room': game_room})
    except GameRoom.DoesNotExist:
        # Handle the case where the room does not exist
        return HttpResponseNotFound("Game room not found.")

@login_required(login_url='login')
@csrf_exempt
def snake(request, room_code):
    try:
        game_room = GameRoom.objects.get(room_code=room_code)
        if not game_room.is_active:
            return redirect('game_lobby', room_code=room_code, game_id=game_room.game.game_id)
        return render(request, 'games/snake.html', {'game_room': game_room})
    except GameRoom.DoesNotExist:
        return HttpResponseNotFound("Game room not found.")

@login_required(login_url='login')
@csrf_exempt
def football(request,room_code):
    pass

# games/views.py
@login_required(login_url='login')
@csrf_exempt
def ludo(request, room_code):
    try:
        game_room = GameRoom.objects.get(room_code=room_code)
        if not game_room.is_active or game_room.game.slug != "ludo":
            return redirect('game_lobby', room_code=room_code, game_id=game_room.game.game_id)
        return render(request, 'games/ludo.html', {'game_room': game_room})
    except GameRoom.DoesNotExist:
        return HttpResponseNotFound("Game room not found.")


@login_required(login_url='login')
@csrf_exempt
def tic_tac_toe(request, room_code):
    try:
        game_room = GameRoom.objects.get(room_code=room_code)
        if not game_room.is_active or game_room.game.slug != "tic-tac-toe":
            return redirect('game_lobby', room_code=room_code, game_id=game_room.game.game_id)
        players = []
        for player in game_room.players.all():
            player_status = PlayerStatus.objects.filter(user=player, game_room=game_room).first()
            players.append({
                'username': player.username,
                'symbol': player_status.current_position.get('symbol', '') if player_status else ''
            })
        return render(request, 'games/tic_tac_toe.html', {
            'game_room': game_room,
            'players': players
        })
    except GameRoom.DoesNotExist:
        return HttpResponseNotFound("Game room not found.")


from django.http import JsonResponse
from .models import GameRoom
@login_required(login_url='login')
@csrf_exempt
def get_players(request, room_code):
    try:
        game_room = GameRoom.objects.get(room_code=room_code)
        players = game_room.players.all()
        return JsonResponse({'players': [p.username for p in players]})
    except GameRoom.DoesNotExist:
        return JsonResponse({'players': []})
    

login_required(login_url='login')
@csrf_exempt
def zombsroyale(request, room_code):
    try:
        game_room = GameRoom.objects.get(room_code=room_code)
        if not game_room.is_active or game_room.game.slug != "zombsroyale":
            return redirect('game_lobby', room_code=room_code, game_id=game_room.game.game_id)
        
        players_with_scores = []
        for player in game_room.players.all():
            player_status = PlayerStatus.objects.filter(user=player, game_room=game_room).first()
            players_with_scores.append({
                'username': player.username,
                'score': player_status.score if player_status else 0,
            })
        return render(request, 'games/zombsroyale.html', {
            'game_room': game_room,
            'players_with_scores': players_with_scores
        })
    except GameRoom.DoesNotExist:
        return HttpResponseNotFound("Game room not found.")

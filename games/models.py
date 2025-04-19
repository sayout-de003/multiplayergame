from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from django.conf import settings
from django.db.models.signals import pre_save
from django.dispatch import receiver
import uuid
import random
import string

# Model to represent the games available on the platform
# Game Model
class Game(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    game_id = models.CharField(max_length=255, primary_key=True)  # Custom ID
    image = models.ImageField(upload_to='game_images/', null=True, blank=True)  # Optional
    slug = models.SlugField(unique=True)
    max_players = models.IntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    playcanvas_project_id = models.CharField(max_length=255, blank=True, null=True)  # Store PlayCanvas project ID
    url = models.URLField(max_length=255, blank=True, null=True)  # Store game URL


    def __str__(self):
        return self.name




# Utility function to generate a unique room code
def generate_unique_room_code():
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not GameRoom.objects.filter(room_code=code).exists():
            return code

# Enum for game room statuses
class GameStatus(models.TextChoices):
    NOT_STARTED = 'Not Started'
    IN_PROGRESS = 'In Progress'
    COMPLETED = 'Completed'

# Model to represent a game room
class GameRoom(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    room_code = models.CharField(max_length=10, unique=True, blank=True, editable=False)
    is_private = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    players = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='game_rooms')
    
    is_started = models.CharField(
        max_length=15,
        choices=GameStatus.choices,
        default=GameStatus.NOT_STARTED
    )
    max_players = models.PositiveIntegerField(default=4)
    is_active = models.BooleanField(default=True)
    is_starting = models.BooleanField(default=False)
    start_time = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.game.name} - {self.room_code}"

    def save(self, *args, **kwargs):
        if not self.room_code:
            self.room_code = generate_unique_room_code().upper()
        super().save(*args, **kwargs)

    def add_player(self, user):
        if self.players.count() < self.max_players:
            self.players.add(user)
        else:
            raise ValueError("Room is full.")

# Model to track player readiness in a game room
# Model to track player readiness in a game room
# games/models.py (Update PlayerStatus)
class PlayerStatus(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    game_room = models.ForeignKey(GameRoom, on_delete=models.CASCADE)
    score = models.IntegerField(default=0)
    current_position = models.JSONField(default=dict)  # For Ludo: {"piece1": 0, "piece2": 0, "piece3": 0, "piece4": 0}
    is_ready = models.BooleanField(default=False)  # Track if player is ready to start
    color = models.CharField(max_length=20, blank=True, null=True)  # Ludo player color (e.g., red, blue, green, yellow)
    last_active = models.DateTimeField(auto_now=True)  # Automatically updates on save

    class Meta:
        unique_together = ('user', 'game_room')

    def __str__(self):
        return f"{self.user.username} - {self.game_room.room_code}"
# Model to log player actions in a game room
class ActivityLog(models.Model):
    game_room = models.ForeignKey(GameRoom, on_delete=models.CASCADE)
    player = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    action = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.player.username} in {self.game_room.room_code} - {self.action}"


from django.db import models
from django.conf import settings  # Import settings to access AUTH_USER_MODEL

class Snake(models.Model):
    player = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)  # Correct reference to User model
    game_room = models.ForeignKey('GameRoom', on_delete=models.CASCADE)
    length = models.IntegerField(default=1)
    body_positions = models.JSONField(default=list)
    direction = models.CharField(max_length=10, default='up')
    color = models.CharField(max_length=20, default='green')
    is_alive = models.BooleanField(default=True)
    score = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.player.username}'s Snake in Room {self.game_room.id}"







# Choices for Game Types
GAME_TYPE_CHOICES = [
    ('3v3', '3v3'),
    ('5v5', '5v5'),
    ('6v6', '6v6'),  # Default option for standard gameplay
]

# Roles for Football Players
PLAYER_ROLES = [
    ('GK', 'Goalkeeper'),
    ('DEF', 'Defender'),
    ('MID', 'Midfielder'),
    ('FWD', 'Forward'),
]


# Football Room Model
class FootballRoom(models.Model):
    name = models.CharField(max_length=100, unique=True)
    room_code = models.CharField(max_length=10, unique=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='football_room_profile')

    game_type = models.CharField(max_length=4, choices=GAME_TYPE_CHOICES, default='6v6')
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=15,
        choices=GameStatus.choices,
        default=GameStatus.NOT_STARTED
    )
    is_private = models.BooleanField(default=False)
    password = models.CharField(max_length=50, blank=True, null=True)  # For private rooms, optional
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_football_rooms')

    def __str__(self):
        return f"Football Room: {self.name} (Code: {self.room_code}, Type: {self.game_type})"

    def get_team_distribution(self):
        # Get current player counts for each team
        team_a = FootballPlayer.objects.filter(room=self, team='A').count()
        team_b = FootballPlayer.objects.filter(room=self, team='B').count()
        return team_a, team_b

    def validate_team_distribution(self):
        # Ensure both teams are balanced
        team_a, team_b = self.get_team_distribution()
        max_team_size = self.get_max_players() // 2
        if team_a > max_team_size or team_b > max_team_size:
            raise ValueError("Team distribution is unbalanced.")



class FootballPlayer(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='football_player_profile')
    room = models.ForeignKey(FootballRoom, on_delete=models.CASCADE, related_name='players')
    team = models.CharField(max_length=1, choices=[('A', 'Team A'), ('B', 'Team B')], null=True, blank=True)
    role = models.CharField(max_length=3, choices=PLAYER_ROLES, null=True, blank=True)  # Player's role in the team
    x_position = models.FloatField(default=0.0)  # Player's X-coordinate
    y_position = models.FloatField(default=0.0)  # Player's Y-coordinate
    color = models.CharField(max_length=20, default="blue")  # Player's color on the field
    score = models.IntegerField(default=0)  # Player's score (e.g., goals)

    def __str__(self):
        return f"{self.user.username} in Room {self.room.room_code} (Team {self.team}, Role: {self.role})"

    def assign_team(self, preferred_team=None):
        # Assign team to the player
        if self.room.is_private and preferred_team in ['A', 'B']:
            # For private rooms, allow user to select their team
            team_a, team_b = self.room.get_team_distribution()
            max_team_size = self.room.get_max_players() // 2
            if preferred_team == 'A' and team_a < max_team_size:
                self.team = 'A'
            elif preferred_team == 'B' and team_b < max_team_size:
                self.team = 'B'
            else:
                raise ValueError(f"Team {preferred_team} is full.")
        else:
            # Auto-assign team if not a private room or preferred team not specified
            team_a, team_b = self.room.get_team_distribution()
            max_team_size = self.room.get_max_players() // 2
            if team_a < max_team_size:
                self.team = 'A'
            elif team_b < max_team_size:
                self.team = 'B'
            else:
                raise ValueError("No available slots in either team.")
        self.save()

    def assign_role(self):
        # Assign roles dynamically to ensure fair distribution
        team_players = FootballPlayer.objects.filter(room=self.room, team=self.team)
        assigned_roles = [player.role for player in team_players if player.role]

        # Determine role priorities
        max_team_size = self.room.get_max_players() // 2
        roles_distribution = ['GK'] + ['DEF'] * (max_team_size // 3) + \
                             ['MID'] * (max_team_size // 3) + \
                             ['FWD'] * (max_team_size - 1 - (max_team_size // 3) * 2)

        # Ensure no duplicate roles beyond limits
        for role in assigned_roles:
            if role in roles_distribution:
                roles_distribution.remove(role)

        if roles_distribution:
            self.role = roles_distribution.pop(0)  # Assign the first available role
        else:
            raise ValueError("No roles available for this player.")
        self.save()


# Football Ball Model
class FootballBall(models.Model):
    room = models.OneToOneField(FootballRoom, on_delete=models.CASCADE, related_name='football_ball')
    x_position = models.FloatField(default=50.0)  # Ball's X-coordinate (centered by default)
    y_position = models.FloatField(default=50.0)  # Ball's Y-coordinate (centered by default)
    radius = models.FloatField(default=5.0)  # Ball's size

    def __str__(self):
        return f"Ball in Room {self.room.room_code} at ({self.x_position}, {self.y_position})"


# Match Score Model
class FootballMatchScore(models.Model):
    room = models.OneToOneField(FootballRoom, on_delete=models.CASCADE, related_name='match_score')
    team_a_score = models.PositiveIntegerField(default=0)
    team_b_score = models.PositiveIntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Score for Room {self.room.room_code}: Team A {self.team_a_score} - Team B {self.team_b_score}"


# Player Activity Log Model
class PlayerActivityLog(models.Model):
    room = models.ForeignKey(FootballRoom, on_delete=models.CASCADE, related_name='activity_logs')
    player = models.ForeignKey(FootballPlayer, on_delete=models.CASCADE, related_name='activity_logs')
    action = models.TextField()  # Description of the player's action (e.g., "scored a goal", "moved to position")
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.player.user.username}: {self.action} at {self.timestamp}"


from django.db import models

class NewModel(models.Model):  # ← This must inherit from models.Model
    name = models.CharField(max_length=100)
const canvas = document.getElementById("gameCanvas");
const ctx = canvas.getContext("2d");

const roomCode = "default_room"; // Change based on dynamic room code
const ws = new WebSocket(`ws://localhost:8000/ws/snake-game/${roomCode}/`);

let players = {};
let direction = { x: 1, y: 0 };

// Handle incoming messages
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "game_state") {
        players = data.players;
    }
};

// Update snake movement
function moveSnake() {
    ws.send(JSON.stringify({
        type: "snake_update",
        snake: players[ws.id]?.snake.map(seg => ({
            x: seg.x + direction.x * 10,
            y: seg.y + direction.y * 10,
        })),
        direction
    }));
}

// Listen for keyboard input
document.addEventListener("keydown", (event) => {
    if (event.key === "ArrowUp" && direction.y === 0) direction = { x: 0, y: -1 };
    if (event.key === "ArrowDown" && direction.y === 0) direction = { x: 0, y: 1 };
    if (event.key === "ArrowLeft" && direction.x === 0) direction = { x: -1, y: 0 };
    if (event.key === "ArrowRight" && direction.x === 0) direction = { x: 1, y: 0 };
});

// Game loop
function gameLoop() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    Object.values(players).forEach(player => {
        ctx.fillStyle = "lime";
        player.snake.forEach(segment => {
            ctx.fillRect(segment.x, segment.y, 10, 10);
        });
    });

    moveSnake();
    requestAnimationFrame(gameLoop);
}

// Start the game
gameLoop();

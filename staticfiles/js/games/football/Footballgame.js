// Footballgame.js

const roomCode = prompt("Enter Room Code:");
const socket = new WebSocket(`ws://${window.location.host}/ws/football/${roomCode}/`);
let myPlayerId = null;
let myTeam = null;
let isAssigned = false; // Track assignment status

const initialGameState = {
    players: {
        "A_gk": { x: 50, y: 300, team: "A", role: "goalkeeper" },
        "A_1": { x: 200, y: 150, team: "A", role: "field" },
        "A_2": { x: 200, y: 300, team: "A", role: "field" },
        "A_3": { x: 200, y: 450, team: "A", role: "field" },
        "A_4": { x: 350, y: 300, team: "A", role: "field" },
        "B_gk": { x: 950, y: 300, team: "B", role: "goalkeeper" },
        "B_1": { x: 800, y: 150, team: "B", role: "field" },
        "B_2": { x: 800, y: 300, team: "B", role: "field" },
        "B_3": { x: 800, y: 450, team: "B", role: "field" },
        "B_4": { x: 650, y: 300, team: "B", role: "field" }
    },
    ball: { x: 500, y: 300, vx: 0, vy: 0 },
    scores: { A: 0, B: 0 }
};

let gameState = JSON.parse(JSON.stringify(initialGameState));

// WebSocket Handlers
socket.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log("Received:", data); // Debug every message
    switch (data.type) {
        case "assign_player":
            myPlayerId = data.player_id;
            myTeam = data.team;
            isAssigned = true;
            gameState = mergeGameState(gameState, data.game_state);
            console.log(`Assigned: ${myPlayerId} to Team ${myTeam}`);
            updateScoreboard();
            break;
        case "state_update":
            const newState = mergeGameState(gameState, data.game_state);
            if (myPlayerId && newState.players[myPlayerId]) {
                newState.players[myPlayerId].x = gameState.players[myPlayerId].x;
                newState.players[myPlayerId].y = gameState.players[myPlayerId].y;
            }
            gameState = newState;
            updateScoreboard();
            break;
        default:
            console.warn("Unknown message type:", data.type);
    }
};

socket.onerror = function(error) {
    console.error("WebSocket error:", error);
    alert("WebSocket error occurred. Check console.");
};

socket.onclose = function(event) {
    console.error("WebSocket closed:", event.code, event.reason);
    alert(`Connection closed. Code: ${event.code}`);
};

socket.onopen = function() {
    console.log("WebSocket connected");
    socket.send(JSON.stringify({ type: "join" })); // Request assignment
};

// Merge game state, preserving local player position
function mergeGameState(currentState, serverState) {
    const mergedPlayers = { ...currentState.players };
    for (let id in serverState.players) {
        mergedPlayers[id] = { ...currentState.players[id], ...serverState.players[id] };
    }
    return {
        ball: { ...currentState.ball, ...serverState.ball },
        scores: { ...currentState.scores, ...serverState.scores },
        players: mergedPlayers
    };
}

function sendPlayerMove(direction) {
    const player = gameState.players[myPlayerId];
    if (!player || player.team !== myTeam || player.role === "goalkeeper") return;

    const newX = Math.max(15, Math.min(canvas.width - 15, player.x + direction.x));
    const newY = Math.max(15, Math.min(canvas.height - 15, player.y + direction.y));

    player.x = newX;
    player.y = newY;

    socket.send(JSON.stringify({
        type: "player_move",
        player_id: myPlayerId,
        movement: { x: newX, y: newY }
    }));
}

// Game Setup
const canvas = document.getElementById("gameCanvas");
if (!canvas) throw new Error("Canvas not found");
const ctx = canvas.getContext("2d");
if (!ctx) throw new Error("Context not available");

canvas.width = 1000;
canvas.height = 600;

let keys = {};

window.addEventListener("keydown", (e) => {
    keys[e.key] = true;
    handlePlayerInput();
});

window.addEventListener("keyup", (e) => {
    keys[e.key] = false;
    handlePlayerInput();
});

canvas.addEventListener("click", (e) => {
    if (!isAssigned || !myTeam) {
        console.log("Cannot select player: Waiting for team assignment...");
        return;
    }

    const rect = canvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    for (let id in gameState.players) {
        const player = gameState.players[id];
        if (player.team !== myTeam || player.role === "goalkeeper") continue;

        const dx = clickX - player.x;
        const dy = clickY - player.y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance < 20) {
            myPlayerId = id;
            console.log("Switched to player:", myPlayerId);
            return;
        }
    }
});

function update() {
    moveBall();
    moveGoalkeepers();
    checkCollisions();
    drawGame();
    requestAnimationFrame(update);
}

function handlePlayerInput() {
    if (!isAssigned || !myPlayerId || !gameState.players[myPlayerId] || gameState.players[myPlayerId].team !== myTeam) {
        console.log("Cannot move: Player not assigned yet or invalid");
        return;
    }

    const speed = 5;
    const direction = { x: 0, y: 0 };

    if (keys["ArrowUp"]) direction.y = -speed;
    if (keys["ArrowDown"]) direction.y = speed;
    if (keys["ArrowLeft"]) direction.x = -speed;
    if (keys["ArrowRight"]) direction.x = speed;
    if (keys[" "]) kickBall();

    if (direction.x !== 0 || direction.y !== 0) {
        sendPlayerMove(direction);
    }
}

function moveBall() {
    gameState.ball.x += gameState.ball.vx;
    gameState.ball.y += gameState.ball.vy;
    
    gameState.ball.vx *= 0.98;
    gameState.ball.vy *= 0.98;
    
    if (gameState.ball.y <= 10) {
        gameState.ball.y = 10;
        gameState.ball.vy = Math.abs(gameState.ball.vy) * 0.8;
    }
    if (gameState.ball.y >= canvas.height - 10) {
        gameState.ball.y = canvas.height - 10;
        gameState.ball.vy = -Math.abs(gameState.ball.vy) * 0.8;
    }
    if (gameState.ball.x <= 10) {
        gameState.ball.x = 10;
        gameState.ball.vx = Math.abs(gameState.ball.vx) * 0.8;
    }
    if (gameState.ball.x >= canvas.width - 10) {
        gameState.ball.x = canvas.width - 10;
        gameState.ball.vx = -Math.abs(gameState.ball.vx) * 0.8;
    }
}

function moveGoalkeepers() {
    const goalTop = canvas.height / 2 - 100;
    const goalBottom = canvas.height / 2 + 100;

    for (let id in gameState.players) {
        const player = gameState.players[id];
        if (player.role !== "goalkeeper") continue;

        player.x = player.team === "A" ? 30 : canvas.width - 30;
        player.direction = player.direction || 1;
        player.speed = player.speed || 2;
        
        player.y += player.speed * player.direction;
        
        if (player.y <= goalTop + 20) {
            player.y = goalTop + 20;
            player.direction = 1;
        }
        if (player.y >= goalBottom - 20) {
            player.y = goalBottom - 20;
            player.direction = -1;
        }
    }
}

function checkCollisions() {
    for (let id in gameState.players) {
        const player = gameState.players[id];
        const dx = gameState.ball.x - player.x;
        const dy = gameState.ball.y - player.y;
        const distance = Math.sqrt(dx * dx + dy * dy);
        const minDistance = player.role === "goalkeeper" ? 30 : 25;

        if (distance < minDistance) {
            const angle = Math.atan2(dy, dx);
            const force = player.role === "goalkeeper" ? 0.5 : 0.2;
            
            gameState.ball.vx = Math.cos(angle) * force * 10;
            gameState.ball.vy = Math.sin(angle) * force * 10;
            
            gameState.ball.x = player.x + Math.cos(angle) * minDistance;
            gameState.ball.y = player.y + Math.sin(angle) * minDistance;
            
            socket.send(JSON.stringify({
                type: "ball_update",
                ball: gameState.ball
            }));
        }
    }

    if (gameState.ball.x <= 30 && 
        gameState.ball.y > canvas.height / 2 - 100 && 
        gameState.ball.y < canvas.height / 2 + 100) {
        const goalkeeperA = gameState.players["A_gk"];
        if (Math.abs(gameState.ball.y - goalkeeperA.y) > 30) {
            gameState.scores.B++;
            resetBall();
            socket.send(JSON.stringify({
                type: "score_update",
                scores: gameState.scores
            }));
        }
    }
    if (gameState.ball.x >= canvas.width - 30 && 
        gameState.ball.y > canvas.height / 2 - 100 && 
        gameState.ball.y < canvas.height / 2 + 100) {
        const goalkeeperB = gameState.players["B_gk"];
        if (Math.abs(gameState.ball.y - goalkeeperB.y) > 30) {
            gameState.scores.A++;
            resetBall();
            socket.send(JSON.stringify({
                type: "score_update",
                scores: gameState.scores
            }));
        }
    }
}

function kickBall() {
    if (!myPlayerId || !gameState.players[myPlayerId]) return;

    const player = gameState.players[myPlayerId];
    const dx = gameState.ball.x - player.x;
    const dy = gameState.ball.y - player.y;
    const distance = Math.sqrt(dx * dx + dy * dy);

    if (distance < 30) {
        const kickStrength = 10;
        const angle = Math.atan2(dy, dx);
        gameState.ball.vx = Math.cos(angle) * kickStrength;
        gameState.ball.vy = Math.sin(angle) * kickStrength;
        
        socket.send(JSON.stringify({
            type: "ball_update",
            ball: gameState.ball
        }));
    }
}

function resetBall() {
    gameState.ball = { x: canvas.width / 2, y: canvas.height / 2, vx: 0, vy: 0 };
    socket.send(JSON.stringify({
        type: "ball_update",
        ball: gameState.ball
    }));
    updateScoreboard();
}

function updateScoreboard() {
    const teamAScore = document.getElementById("teamAScore");
    const teamBScore = document.getElementById("teamBScore");
    if (teamAScore) teamAScore.textContent = `Team A: ${gameState.scores.A}`;
    if (teamBScore) teamBScore.textContent = `Team B: ${gameState.scores.B}`;
}

function drawGame() {
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#2ecc71";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.fillStyle = "white";
    ctx.fillRect(0, canvas.height / 2 - 100, 30, 200);
    ctx.fillRect(canvas.width - 30, canvas.height / 2 - 100, 30, 200);

    for (let id in gameState.players) {
        const player = gameState.players[id];
        if (!player.x || !player.y) continue;

        ctx.fillStyle = player.team === "A" ? "blue" : "red";
        ctx.beginPath();
        ctx.arc(player.x, player.y, player.role === "goalkeeper" ? 20 : 15, 0, Math.PI * 2);
        ctx.fill();

        if (id === myPlayerId) {
            ctx.strokeStyle = "yellow";
            ctx.lineWidth = 2;
            ctx.stroke();
        }

        ctx.fillStyle = "white";
        ctx.font = "12px Arial";
        ctx.fillText(id, player.x - 10, player.y - 20);
    }

    ctx.fillStyle = "white";
    ctx.beginPath();
    ctx.arc(gameState.ball.x, gameState.ball.y, 10, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = "black";
    ctx.font = "16px Arial";
    ctx.fillText(`My Player: ${myPlayerId || "Not assigned"} (Team ${myTeam || "None"})`, 10, 20);
    if (!isAssigned) {
        ctx.fillStyle = "red";
        ctx.fillText("Waiting for server assignment...", 10, 40);
    }
}

console.log("Starting with:", gameState);
update();
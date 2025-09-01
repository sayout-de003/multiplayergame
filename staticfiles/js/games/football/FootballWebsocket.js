const roomCode = prompt("Enter Room Code:");
const ws = new WebSocket(`ws://${window.location.host}/ws/football/${roomCode}/`);



socket.onmessage = function(event) {
    let data = JSON.parse(event.data);

    if (data.type === "game_state_update") {
        players = data.game_state.players;
        ball = data.game_state.ball;
        scores = data.game_state.scores;
        updateScoreboard();
    }
};

// Send Player Movements to Server
function sendPlayerMove(direction) {
    socket.send(JSON.stringify({ type: "player_move", movement: direction }));
}
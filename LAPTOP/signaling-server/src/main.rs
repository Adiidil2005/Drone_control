/*
 * signaling_server - relays WebRTC SDP offers/answers and ICE candidates
 * between browser controllers and Pi companion computers over a plain
 * WebSocket. Does NOT touch video or control data itself - once the
 * WebRTC peer connection is established, browser and Pi talk directly,
 * peer-to-peer. This process only exists to help them find each other.
 *
 * No auth/RBAC in this version - anyone who can reach this server can
 * register as a drone or request to connect to one. Fine for bench
 * testing on a private network, not fine for anything public-facing.
 * Flagged the same way in README.md.
 */
use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        State,
    },
    response::IntoResponse,
    routing::get,
    Router,
};
use futures_util::{SinkExt, StreamExt};
use serde_json::Value;
use std::{collections::HashMap, sync::Arc};
use tokio::sync::{mpsc, Mutex};

type Registry = Arc<Mutex<HashMap<String, (mpsc::UnboundedSender<Message>, String)>>>; // id -> (sender, role)

#[tokio::main]
async fn main() {
    let registry: Registry = Arc::new(Mutex::new(HashMap::new()));

    let app = Router::new()
        .route("/ws", get(ws_handler))
        .with_state(registry);

    let listener = tokio::net::TcpListener::bind("0.0.0.0:9090")
        .await
        .expect("failed to bind port 9090");
    println!("Signaling server listening on ws://0.0.0.0:9090/ws");
    axum::serve(listener, app).await.expect("server error");
}

async fn ws_handler(ws: WebSocketUpgrade, State(registry): State<Registry>) -> impl IntoResponse {
    ws.on_upgrade(move |socket| handle_socket(socket, registry))
}

async fn handle_socket(socket: WebSocket, registry: Registry) {
    let (mut sink, mut stream) = socket.split();
    let (tx, mut rx) = mpsc::unbounded_channel::<Message>();

    // forwards anything queued for this client out to its actual socket
    let forward_task = tokio::spawn(async move {
        while let Some(msg) = rx.recv().await {
            if sink.send(msg).await.is_err() {
                break;
            }
        }
    });

    let mut my_id: Option<String> = None;

    while let Some(Ok(msg)) = stream.next().await {
        let Message::Text(text) = msg else { continue };
        let Ok(v): Result<Value, _> = serde_json::from_str(&text) else { continue };
        let msg_type = v.get("type").and_then(|t| t.as_str()).unwrap_or("");

        match msg_type {
            "register" => {
                if let Some(id) = v.get("id").and_then(|i| i.as_str()) {
                    let role = v.get("role").and_then(|r| r.as_str()).unwrap_or("controller").to_string();
                    registry.lock().await.insert(id.to_string(), (tx.clone(), role));
                    my_id = Some(id.to_string());
                    println!("registered: {id}");
                }
            }
            "list_drones" => {
                let ids: Vec<String> = registry
                    .lock()
                    .await
                    .iter()
                    .filter(|(_, (_, role))| role == "drone")
                    .map(|(id, _)| id.clone())
                    .collect();
                let resp = serde_json::json!({"type":"drone_list","drones":ids});
                let _ = tx.send(Message::Text(resp.to_string()));
            }
            // SDP offers/answers and ICE candidates all get relayed the same way:
            // look up the intended recipient by id, stamp who it's from, forward verbatim.
            "offer" | "answer" | "ice" => {
                if let Some(target) = v.get("target").and_then(|t| t.as_str()) {
                    let reg = registry.lock().await;
                    if let Some((target_tx, _)) = reg.get(target) {
                        let mut relayed = v.clone();
                        if let Some(obj) = relayed.as_object_mut() {
                            obj.insert(
                                "from".to_string(),
                                serde_json::json!(my_id.clone().unwrap_or_default()),
                            );
                        }
                        let _ = target_tx.send(Message::Text(relayed.to_string()));
                    }
                }
            }
            _ => {}
        }
    }

    if let Some(id) = my_id {
        registry.lock().await.remove(&id);
        println!("disconnected: {id}");
    }
    forward_task.abort();
}

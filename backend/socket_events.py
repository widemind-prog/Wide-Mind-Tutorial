from flask import session
from flask_socketio import join_room
from extensions import socketio
from state import online_users


@socketio.on("connect")
def handle_connect():
    if "user_id" in session:
        user_id = session["user_id"]
        online_users.add(user_id)
        join_room(f"user_{user_id}")


@socketio.on("disconnect")
def handle_disconnect():
    if "user_id" in session:
        online_users.discard(session["user_id"])
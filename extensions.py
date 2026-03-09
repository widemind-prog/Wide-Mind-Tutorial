from flask_socketio import SocketIO, emit, join_room

socketio = SocketIO(cors_allowed_origins="*", async_mode="eventlet", logger=True, engineio_logger=True)
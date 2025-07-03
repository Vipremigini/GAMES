import asyncio
import websockets
import json
import logging

# Configure logging for better visibility
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Dictionary to store active chat rooms.
# Each key is a room code (string), and each value is a set of connected WebSocket clients.
# We will enforce a maximum of 3 users per room.
rooms = {}

async def register(websocket, room_code, user_id):
    """Registers a new WebSocket connection to a specific chat room."""
    if room_code not in rooms:
        rooms[room_code] = set()
        logging.info(f"Room '{room_code}' created.")

    if len(rooms[room_code]) >= 3:
        logging.warning(f"Room '{room_code}' is full. Rejecting user {user_id}.")
        await websocket.send(json.dumps({"type": "error", "message": "Room is full. Maximum 3 users allowed."}))
        return False

    rooms[room_code].add(websocket)
    logging.info(f"User {user_id} registered to room '{room_code}'. Total users in room: {len(rooms[room_code])}")

    # Notify everyone in the room that a new user has joined
    join_message = json.dumps({
        "type": "status",
        "user": "System",
        "text": f"User {user_id} has joined the room."
    })
    await broadcast_message(room_code, join_message, sender_websocket=None) # Send to all, including the new user

    return True

async def unregister(websocket, room_code, user_id):
    """Unregisters a WebSocket connection from a chat room."""
    if room_code in rooms and websocket in rooms[room_code]:
        rooms[room_code].remove(websocket)
        logging.info(f"User {user_id} unregistered from room '{room_code}'. Remaining users: {len(rooms[room_code])}")

        # Notify everyone in the room that a user has left
        leave_message = json.dumps({
            "type": "status",
            "user": "System",
            "text": f"User {user_id} has left the room."
        })
        await broadcast_message(room_code, leave_message, sender_websocket=None)

        if not rooms[room_code]:
            del rooms[room_code]
            logging.info(f"Room '{room_code}' is now empty and has been removed.")

async def broadcast_message(room_code, message, sender_websocket):
    """Sends a message to all clients in a specific room, excluding the sender if specified."""
    if room_code in rooms:
        # Create a list of tasks to send messages concurrently
        send_tasks = []
        for client_websocket in rooms[room_code]:
            if client_websocket != sender_websocket: # Don't send back to the sender if it's a user message
                send_tasks.append(client_websocket.send(message))
        
        if send_tasks:
            await asyncio.gather(*send_tasks)
            logging.info(f"Broadcasted message to room '{room_code}'.")
        else:
            logging.info(f"No other clients to broadcast to in room '{room_code}'.")
    else:
        logging.warning(f"Attempted to broadcast to non-existent room '{room_code}'.")


async def handler(websocket, path):
    """Handles a new WebSocket connection and its messages."""
    room_code = None
    user_id = None
    try:
        # First message from client should be a 'join' message
        initial_message = await websocket.recv()
        data = json.loads(initial_message)

        if data.get("type") == "join" and "code" in data and "userId" in data:
            room_code = data["code"]
            user_id = data["userId"]
            logging.info(f"Attempting to join user {user_id} to room '{room_code}'.")
            
            if not await register(websocket, room_code, user_id):
                # If registration failed (e.g., room full), close connection
                return
        else:
            logging.warning(f"Invalid initial message from {websocket.remote_address}: {initial_message}")
            await websocket.send(json.dumps({"type": "error", "message": "Invalid initial message. Expected 'join' with 'code' and 'userId'."}))
            return

        # Listen for messages from this client
        async for message in websocket:
            data = json.loads(message)
            if data.get("type") == "message" and "text" in data:
                chat_message = json.dumps({
                    "type": "chat",
                    "user": user_id,
                    "text": data["text"]
                })
                logging.info(f"Received message from {user_id} in room '{room_code}': {data['text']}")
                await broadcast_message(room_code, chat_message, sender_websocket=websocket)
            else:
                logging.warning(f"Received unknown message type from {user_id}: {message}")

    except websockets.exceptions.ConnectionClosedOK:
        logging.info(f"Connection closed normally for user {user_id} in room '{room_code}'.")
    except websockets.exceptions.ConnectionClosedError as e:
        logging.error(f"Connection closed with error for user {user_id} in room '{room_code}': {e}")
    except json.JSONDecodeError:
        logging.error(f"Received invalid JSON from {websocket.remote_address}")
    except Exception as e:
        logging.error(f"An unexpected error occurred for user {user_id} in room '{room_code}': {e}", exc_info=True)
    finally:
        if room_code and user_id:
            await unregister(websocket, room_code, user_id)

async def main():
    """Starts the WebSocket server."""
    # Start the server on localhost, port 8765
    # You might need to change 'localhost' to '0.0.0.0' if running in a container or remote server
    # and want to access it from other machines.
    async with websockets.serve(handler, "localhost", 8765):
        logging.info("WebSocket server started on ws://localhost:8765")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Server stopped by user.")
    except Exception as e:
        logging.critical(f"Server crashed: {e}", exc_info=True)


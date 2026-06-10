from fastapi import FastAPI, Request
from dotenv import load_dotenv
from fastapi.responses import PlainTextResponse
import os
import random
from redis import Redis

load_dotenv()
app = FastAPI()

r = Redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379"),
    decode_responses=True,
)

RIDERS = ["Rider 1", "Rider 2", "Rider 3"]
LOCATIONS = ["Town", "Mall", "Hospital", "School"]

SESSION_TTL = 300


def main_menu_text():
    return (
        "CON Welcome to MwiDrive. Please select an option:\n"
        "1. Order a ride\n"
        "2. See riders\n"
        "3. Exit"
    )


def location_picker_text(title):
    lines = [f"CON {title}"]
    for i, loc in enumerate(LOCATIONS, start=1):
        lines.append(f"{i}. {loc}")
    lines.append(f"{len(LOCATIONS) + 1}. Type your own")
    return "\n".join(lines)


def rider_picker_text(title):
    lines = [f"CON {title}"]
    for i, rd in enumerate(RIDERS, start=1):
        lines.append(f"{i}. {rd}")
    return "\n".join(lines)


def confirmation_text(session_id, rider):
    pickup = r.get(f"Session:{session_id}:pickup")
    dropoff = r.get(f"Session:{session_id}:dropoff")
    return (
        f"CON Confirm your ride:\n"
        f"Pickup: {pickup}\n"
        f"Drop-off: {dropoff}\n"
        f"Rider: {rider}\n"
        f"1. Confirm\n"
        f"2. Cancel"
    )


def set_state(session_id, state):
    r.set(f"Session:{session_id}:state", state, ex=SESSION_TTL)


def clear_session(session_id):
    for key in ["state", "pickup", "dropoff", "rider"]:
        r.delete(f"Session:{session_id}:{key}")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ussd")
async def ussd(request: Request):
    data = await request.form()
    session_id = data.get("sessionId")
    phone_number = data.get("phoneNumber")
    text = (data.get("text") or "").strip()

    inputs = text.split("*") if text else []
    last_input = inputs[-1] if inputs else ""

    state = r.get(f"Session:{session_id}:state")
    user_name = r.get(f"User:{phone_number}:name")

    # First request in a session
    if state is None:
        if not user_name:
            response = "CON Welcome to MwiDrive!\nPlease enter your name:"
            set_state(session_id, "register_name")
        else:
            response = main_menu_text()
            set_state(session_id, "main_menu")

    # ---------- Registration ----------
    elif state == "register_name":
        if last_input:
            r.set(f"User:{phone_number}:name", last_input)
            response = "CON Please enter your default location (e.g. Town):"
            set_state(session_id, "register_location")
        else:
            response = "CON Please enter your name:"

    elif state == "register_location":
        if last_input:
            r.set(f"User:{phone_number}:default_location", last_input)
            response = (
                f"CON Welcome, {user_name or last_input}!\n"
                "1. Order a ride\n"
                "2. See riders\n"
                "3. Exit"
            )
            set_state(session_id, "main_menu")
        else:
            response = "CON Please enter your default location:"

    # ---------- Main menu ----------
    elif state == "main_menu":
        if last_input == "1":
            default_loc = r.get(f"User:{phone_number}:default_location") or "not set"
            response = (
                f"CON Pickup location:\n"
                f"1. Use default ({default_loc})\n"
                f"2. Choose another"
            )
            set_state(session_id, "ride_pickup")
        elif last_input == "2":
            response = (
                "CON Available riders:\n"
                + "\n".join(f"{i + 1}. {rd}" for i, rd in enumerate(RIDERS))
                + "\n0. Back to main menu"
            )
            set_state(session_id, "view_riders")
        elif last_input == "3":
            response = "END Thank you for using MwiDrive. Goodbye!"
            clear_session(session_id)
        else:
            response = "CON Invalid option.\n" + main_menu_text().replace("CON ", "")

    # ---------- Ride: pickup ----------
    elif state == "ride_pickup":
        if last_input == "1":
            default_loc = r.get(f"User:{phone_number}:default_location") or "Unknown"
            r.set(f"Session:{session_id}:pickup", default_loc, ex=SESSION_TTL)
            response = location_picker_text("Drop-off location:")
            set_state(session_id, "ride_dropoff")
        elif last_input == "2":
            response = location_picker_text("Choose pickup location:")
            set_state(session_id, "ride_pickup_choose")
        else:
            response = "CON Invalid option.\n1. Use default\n2. Choose another"

    elif state == "ride_pickup_choose":
        if last_input.isdigit():
            idx = int(last_input)
            if 1 <= idx <= len(LOCATIONS):
                r.set(f"Session:{session_id}:pickup", LOCATIONS[idx - 1], ex=SESSION_TTL)
                response = location_picker_text("Drop-off location:")
                set_state(session_id, "ride_dropoff")
            elif idx == len(LOCATIONS) + 1:
                response = "CON Type your pickup location:"
                set_state(session_id, "ride_pickup_custom")
            else:
                response = location_picker_text("Invalid choice. Choose pickup location:")
        else:
            response = location_picker_text("Invalid choice. Choose pickup location:")

    elif state == "ride_pickup_custom":
        if last_input:
            r.set(f"Session:{session_id}:pickup", last_input, ex=SESSION_TTL)
            response = location_picker_text("Drop-off location:")
            set_state(session_id, "ride_dropoff")
        else:
            response = "CON Type your pickup location:"

    # ---------- Ride: drop-off ----------
    elif state == "ride_dropoff":
        if last_input.isdigit():
            idx = int(last_input)
            if 1 <= idx <= len(LOCATIONS):
                r.set(f"Session:{session_id}:dropoff", LOCATIONS[idx - 1], ex=SESSION_TTL)
                response = "CON Choose your rider:\n1. Random rider\n2. Select rider"
                set_state(session_id, "ride_rider_choice")
            elif idx == len(LOCATIONS) + 1:
                response = "CON Type your drop-off location:"
                set_state(session_id, "ride_dropoff_custom")
            else:
                response = location_picker_text("Invalid choice. Drop-off location:")
        else:
            response = location_picker_text("Invalid choice. Drop-off location:")

    elif state == "ride_dropoff_custom":
        if last_input:
            r.set(f"Session:{session_id}:dropoff", last_input, ex=SESSION_TTL)
            response = "CON Choose your rider:\n1. Random rider\n2. Select rider"
            set_state(session_id, "ride_rider_choice")
        else:
            response = "CON Type your drop-off location:"

    # ---------- Ride: rider selection ----------
    elif state == "ride_rider_choice":
        if last_input == "1":
            chosen = random.choice(RIDERS)
            r.set(f"Session:{session_id}:rider", chosen, ex=SESSION_TTL)
            response = confirmation_text(session_id, chosen)
            set_state(session_id, "ride_confirm")
        elif last_input == "2":
            response = rider_picker_text("Select your rider:")
            set_state(session_id, "ride_rider_select")
        else:
            response = "CON Invalid option.\n1. Random rider\n2. Select rider"

    elif state == "ride_rider_select":
        if last_input.isdigit():
            idx = int(last_input)
            if 1 <= idx <= len(RIDERS):
                chosen = RIDERS[idx - 1]
                r.set(f"Session:{session_id}:rider", chosen, ex=SESSION_TTL)
                response = confirmation_text(session_id, chosen)
                set_state(session_id, "ride_confirm")
            else:
                response = rider_picker_text("Invalid choice. Select your rider:")
        else:
            response = rider_picker_text("Invalid choice. Select your rider:")

    # ---------- Ride: confirm ----------
    elif state == "ride_confirm":
        if last_input == "1":
            pickup = r.get(f"Session:{session_id}:pickup")
            dropoff = r.get(f"Session:{session_id}:dropoff")
            rider = r.get(f"Session:{session_id}:rider")
            response = (
                f"END Your ride has been booked!\n"
                f"Rider: {rider}\n"
                f"Pickup: {pickup}\n"
                f"Drop-off: {dropoff}\n"
                f"You will be contacted shortly."
            )
            clear_session(session_id)
        elif last_input == "2":
            response = "END Your ride has been cancelled."
            clear_session(session_id)
        else:
            response = "CON Invalid option.\n1. Confirm\n2. Cancel"

    # ---------- View riders ----------
    elif state == "view_riders":
        if last_input == "0":
            response = main_menu_text()
            set_state(session_id, "main_menu")
        else:
            response = (
                "CON Invalid option.\nAvailable riders:\n"
                + "\n".join(f"{i + 1}. {rd}" for i, rd in enumerate(RIDERS))
                + "\n0. Back to main menu"
            )

    else:
        response = "END An error occurred. Please try again."
        clear_session(session_id)

    return PlainTextResponse(response)

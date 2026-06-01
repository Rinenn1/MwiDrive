from fastapi import FastAPI, Request
from dotenv import load_dotenv
from fastapi.responses import PlainTextResponse
import os
from redis import Redis

load_dotenv()
app = FastAPI()

r = Redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379"),
        decode_responses = True
    )

riders_list = ["Rider 1", "Rider 2", "Rider 3"]

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/ussd")
async def ussd(request: Request):
    data = await request.form()

    session_id = data.get("sessionId")
    phone_number = data.get("phoneNumber")
    text = data.get("text", "").strip()

    inputs = text.split("*") if text else []
    last_input = inputs[-1] if inputs else ""

    state = r.get(f"Session:{session_id}:state")

    

    if state == None:
        response = "CON Welcome to the MwiDrive. Please select an option:\n1. Order a ride\n2. See riders\n3. Exit\n"
        r.set(f"Session:{session_id}:state", "main_menu", ex=120)
    elif state == "main_menu":
        if last_input == "1":
            response = "END Your ride has been ordered. Please wait for a driver to contact you.\n"
            r.delete(f"Session:{session_id}:state")
        elif last_input == "2":
            response = f"CON Here are the available riders: {', '.join(riders_list)}\n"
            response += "0. Back to main menu\n"
            r.set(f"Session:{session_id}:state", "view_riders", ex=120)
        elif last_input == "3":
            response = "END Thank you for using MwiDrive\n"
            r.delete(f"Session:{session_id}:state")
        elif last_input == "0":
            response = "CON Welcome to the MwiDrive. Please select an option:\n1. Order a ride\n2. See riders\n3. Exit\n"
            r.set(f"Session:{session_id}:state", "main_menu", ex=120)
        else:
            response = "CON Invalid option. Please select an option:\n1. Order a ride\n2. See riders\n3. Exit\n"
            r.set(f"Session:{session_id}:state", "main_menu", ex=120)
    elif state == "view_riders":
        if last_input == "0":
            response = "CON Welcome to the MwiDrive. Please select an option:\n1. Order a ride\n2. See riders\n3. Exit\n"
            r.set(f"Session:{session_id}:state", "main_menu", ex=120)
        else:
            response = "CON Invalid option. Please try again.\n"
            response += f"Here are the available riders: {', '.join(riders_list)}\n"
            response += "0. Back to main menu\n"
            r.set(f"Session:{session_id}:state", "view_riders", ex=120)
    else:
        response = "END An error occurred. Please try again.\n"
        r.delete(f"Session:{session_id}:state")

    return PlainTextResponse(response)

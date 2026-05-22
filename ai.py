from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

SYSTEM_PROMPT = """
You are a friendly booking assistant for a dental clinic. 
Your job is to collect the following information from the patient one step at a time:
1. Full name
2. Phone number
3. Service needed (checkup, cleaning, toothache, filling, etc.)
4. Preferred date (ask them to give a date like 2026-05-25)
5. Preferred time (morning or afternoon)

Rules:
- Ask one question at a time
- Be friendly and professional
- You can respond in Khmer or English depending on what the patient uses
- Once you have all 5 pieces of information, summarize the booking and end with the exact line:
  BOOKING_COMPLETE|name|phone|service|date|time
  Example: BOOKING_COMPLETE|Sok Dara|012345678|Checkup|2026-05-25|Morning
- Do not make up information, always ask the patient
"""

conversations = {}

def chat(user_id, message):
    if user_id not in conversations:
        conversations[user_id] = []
    
    conversations[user_id].append({"role": "user", "parts": [message]})
    
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=conversations[user_id],
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT)
    )
    
    reply = response.text
    conversations[user_id].append({"role": "model", "parts": [reply]})
    return reply

def clear_conversation(user_id):
    if user_id in conversations:
        del conversations[user_id]
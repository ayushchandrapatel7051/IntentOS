import os, sys
sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv()

from google import genai
from google.genai import types as gt

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

SYSTEM = """\
You are IntentOS Planner. Convert user intents into JSON action plans.

SKILLS:
  browser   : navigate(url) | search(query)
  terminal  : execute(command)
  apps      : open_app(name, wait_seconds=2) | press_keys(keys=[...]) | type_text(text)
  messaging : send_message(app, contact, text) | open_chat(app, contact)  [app="whatsapp" or "telegram"]
  vision    : capture_screen() | click_at(x,y)

RULES:
  - Prefer apps > vision
  - Messaging via desktop app shortcuts, never a bot API"""

USER = """\
INTENT: {intent}

Respond with ONLY this JSON (no markdown, no extra text):
{"summary":"one-line description","steps":[{"id":"step_1","skill":"<skill>","action":"<action>","params":{...},"description":"what this step does","reasoning":"why"}]}"""

for intent in ["open notepad", "send hey to Jaidev on whatsapp"]:
    print(f"\n=== INTENT: {intent} ===")
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=USER.format(intent=intent),
        config=gt.GenerateContentConfig(
            system_instruction=SYSTEM,
            temperature=0.1,
            max_output_tokens=512,
        )
    )
    print(resp.text[:400])

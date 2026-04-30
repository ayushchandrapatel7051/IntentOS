from google import genai

client = genai.Client(
    vertexai=True,
    project="intentos-494911",
    location="us-central1"
)

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Explain AI agents"
)

print(response.text)
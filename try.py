import google.generativeai as genai

genai.configure(api_key="AIzaSyAg3dbb8TW8VykCaAThhxyEpxM90jB0-RQ")

model = genai.GenerativeModel("gemini-2.0-flash")

response = model.generate_content("jawab: apa itu python?")
print(response.text)
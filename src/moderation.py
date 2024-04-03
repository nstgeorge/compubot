from openai import OpenAI

client = OpenAI()

def flagged_by_moderation(prompt: str):
  response = client.moderations.create(input=prompt)
  return response.results[0].flagged
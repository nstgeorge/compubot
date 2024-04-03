from openai import OpenAI

client = OpenAI()

def flagged_by_moderation(prompt: str):
  print(prompt)
  response = client.moderations.create(input=prompt)
  print(response.results[0].flagged)
  return response.results[0].flagged
import os
from typing import TypedDict

from pymongo import MongoClient

CONNECTION_URL = os.getenv("MONGODB_URL")
DB_NAME = os.getenv("MONGODB_DB_NAME")

def get_database():
  client = MongoClient(CONNECTION_URL)
  return client[DB_NAME]
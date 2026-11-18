import os

from langchain.chat_models import init_chat_model

from utils.env import load_env

load_env()

model = init_chat_model(
    model=os.getenv("LLM_QWEN_MAX"),
    model_provider="openai",
)

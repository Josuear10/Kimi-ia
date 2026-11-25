"""Local development server: `python main.py` -> http://127.0.0.1:8000"""

import logging

import uvicorn

from app import app

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="127.0.0.1", port=8000)

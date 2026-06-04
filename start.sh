#!/bin/bash
uvicorn api.index:app --host 0.0.0.0 --port ${PORT:-8000}
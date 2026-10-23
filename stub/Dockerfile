FROM python:3.12-slim
WORKDIR /app
RUN pip install fastapi uvicorn --no-cache-dir -q
COPY stub_server.py .
EXPOSE 8001
CMD ["uvicorn", "stub_server:app", "--host", "0.0.0.0", "--port", "8001"]

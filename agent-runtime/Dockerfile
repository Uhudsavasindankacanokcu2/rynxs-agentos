FROM python:3.12-slim
WORKDIR /opt/agent
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY universe_agent/ universe_agent/
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "universe_agent.runtime"]

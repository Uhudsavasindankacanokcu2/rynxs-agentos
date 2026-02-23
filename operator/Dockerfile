FROM python:3.12-slim
WORKDIR /opt/operator
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY universe_operator/ universe_operator/
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "universe_operator.main"]

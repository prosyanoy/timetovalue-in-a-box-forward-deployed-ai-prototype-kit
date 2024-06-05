FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY ttv ./ttv
RUN useradd --uid 10001 --no-create-home ttv
USER 10001
EXPOSE 8080 8081
CMD ["python", "-m", "ttv.service"]

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm fonts-dejavu-core fonts-liberation && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY renderer_tools/package.json renderer_tools/package-lock.json ./renderer_tools/
RUN npm --prefix renderer_tools ci --omit=dev
COPY . .
RUN python renderer_tools/check_math.py
ENV PORT=8080
EXPOSE 8080
CMD ["python", "-u", "webapp.py"]

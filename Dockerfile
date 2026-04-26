# Use the official Microsoft Playwright image rigidly fixing native Chromium dependencies safely
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

# Lock execution to a restricted non-root user avoiding arbitrary OS escalations
RUN useradd -ms /bin/bash nightion_sandbox
USER nightion_sandbox
WORKDIR /home/nightion_sandbox/app

# Copy rigid dependency locks completely locally
COPY requirements.txt .

# Install explicitly pinned local Python requirements structurally bridging offline bounds
RUN pip install --no-cache-dir -r requirements.txt

# Copy the execution architecture natively offline cleanly
COPY . .

# Sandbox Entrypoint mapping internal Python execution natively without exposing OS networking explicitly
CMD ["python", "server.py"]

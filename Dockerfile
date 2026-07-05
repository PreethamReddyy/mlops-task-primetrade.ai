FROM python:3.9-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and required input files
COPY run.py config.yaml data.csv ./

# Default command: run the job with relative paths (no hardcoded absolute paths),
# then print the resulting metrics.json to stdout.
CMD ["sh", "-c", "python run.py --input data.csv --config config.yaml --output metrics.json --log-file run.log && cat metrics.json"]

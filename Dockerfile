FROM heroku/python:3.10

# Install system dependencies
RUN apt-get update && apt-get install -y \
  libopus0 \
  libopus-dev \
  && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Make scripts executable
RUN chmod +x scripts/*.sh

# Apply patches
RUN ./scripts/apply_patches.sh

# Set environment variables
ENV PORT=8000

# Run the application
CMD python src/main.py 
# Use the official Python 3.11 image (slim version for a smaller footprint)
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file first (this caches the installation step to save time later)
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your project files into the container
COPY . .

# Default command (opens an interactive Python shell if no script is specified)
CMD ["python"]
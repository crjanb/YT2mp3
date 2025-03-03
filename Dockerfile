# Use a Python slim image for a smaller Docker image size
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Copy your requirements file into the container
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose port (optional, used if you're running a web service on a specific port)
EXPOSE 8000

# Command to run your application
CMD ["python", "app.py"]

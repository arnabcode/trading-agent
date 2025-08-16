# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables for best practices
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Copy shared models and configs first for better layer caching
COPY ./shared /app/shared
COPY ./configs /app/configs

# Copy the application-specific code for the risk model
COPY ./risk_model_py /app/risk_model_py

# Install the Python dependencies
RUN pip install --no-cache-dir -r /app/risk_model_py/requirements.txt

# Expose the port the app runs on. 8080 is standard for Cloud Run.
EXPOSE 8080

# The command to run the application using uvicorn.
CMD ["uvicorn", "risk_model_py.main:app", "--host", "0.0.0.0", "--port", "8080"]

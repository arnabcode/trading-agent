# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables for best practices
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Copy the shared models directory first. This layer is cached if the shared code doesn't change.
COPY ./shared /app/shared

# Copy the application-specific code for the alpha model
COPY ./alpha_model_py /app/alpha_model_py

# Install the Python dependencies
RUN pip install --no-cache-dir -r /app/alpha_model_py/requirements.txt

# Expose the port the app runs on. 8080 is standard for Cloud Run.
EXPOSE 8080

# The command to run the application using uvicorn.
# This starts the web server and points it to the FastAPI instance named 'app'
# inside the 'alpha_model_py/main.py' file.
CMD ["uvicorn", "alpha_model_py.main:app", "--host", "0.0.0.0", "--port", "8080"]

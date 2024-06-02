# Use the official Python image from the Docker Hub
FROM python:3.9-slim

# Install poetry
RUN pip install poetry

# Set the working directory in the container
WORKDIR /app

# Copy the poetry files into the container
COPY pyproject.toml poetry.lock ./

# Install dependencies using Poetry
RUN poetry install --no-root

# Copy the rest of the application code into the container
COPY gistapi ./gistapi

ENV FLASK_APP=gistapi.gistapi

# Copy the entry point script into the container
COPY entrypoint.sh /entrypoint.sh

# Make the entry point script executable
RUN chmod +x /entrypoint.sh

# Expose the port that the Flask app runs on
EXPOSE 9876

# Use the entry point script to start the application
ENTRYPOINT ["/entrypoint.sh"]

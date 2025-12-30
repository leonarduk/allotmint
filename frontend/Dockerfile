FROM node:20-slim

WORKDIR /app

# Install dependencies first (for better caching)
COPY package*.json ./
RUN npm ci

# Copy application code
COPY . .

# Expose port
EXPOSE 3000

# Run the application
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

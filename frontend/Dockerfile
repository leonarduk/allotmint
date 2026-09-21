FROM node:24-slim

WORKDIR /app

# Install dependencies first (for better caching)
COPY package*.json ./
RUN npm ci

# Copy application code
COPY . .

# Expose the Vite dev server port (2568 = ALOT on a phone keypad, #7811)
EXPOSE 2568

# Run the application
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

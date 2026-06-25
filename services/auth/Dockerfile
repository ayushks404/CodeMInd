FROM node:20-slim

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# FIX: was EXPOSE 5002 — auth service runs on 5001
EXPOSE 5001

CMD ["node", "server.js"]

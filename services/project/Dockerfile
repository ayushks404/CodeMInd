FROM node:20-slim

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# FIX: was EXPOSE 3002 — project service runs on 5002
EXPOSE 5002

CMD ["node", "server.js"]

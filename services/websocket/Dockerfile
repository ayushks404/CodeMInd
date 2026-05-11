FROM node:20-slim

WORKDIR /app

COPY package.json .
RUN npm install

COPY . .

EXPOSE 5004

CMD ["node", "src/server.js"]
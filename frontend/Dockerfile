FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY . .
RUN npm run build && chown -R node:node /app
USER node
EXPOSE 5175
CMD ["npm", "run", "dev"]

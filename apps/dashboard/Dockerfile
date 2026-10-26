# Build context is the repository root (see docker-compose.yml).
FROM node:22-alpine
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY apps/dashboard/package.json apps/dashboard/package-lock.json* ./
RUN npm install
COPY apps/dashboard/ .
RUN npm run build
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
CMD ["npm", "run", "start"]

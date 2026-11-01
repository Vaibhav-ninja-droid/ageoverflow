#!/bin/sh
set -e

docker rm -f ageoverflow-api-container 2>/dev/null || true
docker rm -f ageoverflow-db 2>/dev/null || true
docker build -t ageoverflow-api .
docker run -d \
  --name ageoverflow-db \
  -e POSTGRES_DB=ageoverflow \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  postgres:17

sleep 8

docker run -d \
  --name ageoverflow-api-container \
  --link ageoverflow-db:ageoverflow-db \
  -p 8080:8080 \
  -e DATABASE_URL=postgresql://postgres:postgres@ageoverflow-db:5432/ageoverflow \
  -e SQS_QUEUE_URL=local-disabled \
  ageoverflow-api
  
sleep 5
docker logs ageoverflow-api-container
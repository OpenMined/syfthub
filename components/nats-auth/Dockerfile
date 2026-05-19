# syfthub nats-auth — NATS auth-callout service
FROM golang:1.23-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -o /nats-auth .

FROM alpine:3.20
RUN adduser -D -u 1000 svc
USER svc
COPY --from=build /nats-auth /usr/local/bin/nats-auth
ENTRYPOINT ["nats-auth"]

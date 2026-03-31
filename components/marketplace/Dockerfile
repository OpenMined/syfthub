FROM golang:1.22-alpine AS builder

RUN apk add --no-cache gcc musl-dev

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=1 go build -o marketplace-server .

FROM alpine:3.19
RUN apk add --no-cache sqlite-libs ca-certificates curl
COPY --from=builder /app/marketplace-server /usr/local/bin/marketplace-server

EXPOSE 8003

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1

ENTRYPOINT ["marketplace-server"]

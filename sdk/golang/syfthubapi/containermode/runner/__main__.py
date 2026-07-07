"""Container runner entry point."""
import argparse


def main():
    parser = argparse.ArgumentParser(description="SyftHub Container Runner")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument(
        "--handler",
        default="/app/endpoint/runner.py",
        help="Path to handler module",
    )
    args = parser.parse_args()

    from .server import ContainerRunnerServer

    server = ContainerRunnerServer(args.handler, args.host, args.port)
    server.run()


if __name__ == "__main__":
    main()

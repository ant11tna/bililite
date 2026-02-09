from .push import load_config, send_daily_push


def main() -> int:
    config = load_config()
    return send_daily_push(config)


if __name__ == "__main__":
    raise SystemExit(main())

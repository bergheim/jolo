import uvicorn

from {{PROJECT_NAME_UNDERSCORE}}.app import app


def main() -> None:
    uvicorn.run("{{PROJECT_NAME_UNDERSCORE}}.app:app", host="0.0.0.0", port=int(__import__("os").environ.get("PORT", "4000")), reload=True)


if __name__ == "__main__":
    main()

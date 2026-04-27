from importlib.metadata import PackageNotFoundError, version


def on_page_markdown(markdown, **_):
    try:
        v = "v" + version("oops")
    except PackageNotFoundError:
        v = "latest"
    return markdown.replace("{oops_version}", v)

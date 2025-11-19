from pathlib import Path

import fixit


def run_rules(paths: list):
    for res in fixit.fixit_paths([Path(path) for path in paths]):
        fixit.print_result(res)

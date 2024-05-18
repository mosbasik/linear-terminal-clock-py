

Reference of the lifecycle of various versions of the Python language: https://devguide.python.org/versions/


Guide I'm using for how to package this: https://cjolowicz.github.io/posts/hypermodern-python-01-setup/


1. Use your system package manager to install `pyenv`, `pipx` and [the packages pyenv says your system needs in order to build Python](https://github.com/pyenv/pyenv/wiki#suggested-build-environment)
1. Use `pyenv install` to install the versions of Python you want to develop in (and test against)
    - `$ pyenv install 3.9`
    - `$ pyenv install 3.10`
    - `$ pyenv install 3.11`
    - `$ pyenv install 3.12`
1. Navigate to the root of the repo
1. Use `pyenv local` to configure the versions of Python associated with this repo (the first one will be the default one)
    - `$ pyenv local 3.9 3.10 3.11 3.12`
1. Use `pipx` to install `poetry` using the default version of Python (If you use poetry for other projects that use a different version of Python... I guess just blow that poetry away and install this one, and then do the reverse when you work on the other project.)
    - `$ pipx uninstall poetry`
    - `$ pipx install poetry --python $(pyenv which python)`
1. [When I was creating the project, but probably never again] Use `poetry init` to bootstrap the project
    - `$ poetry init --no-interaction`
1. Use `poetry install` to install the virtual environment
    - `$ poetry install`
1. [When I'm adding libraries to the project's venv] Use `poetry add` to add libraries (no need to run `poetry install` afterwards; they go into the venv right away)
    - `$ poetry add blessed`
    - `$ poetry add skyfield`
    - `$ poetry add tzlocal`
    - `$ poetry add memoization`
    - `$ poetry add structlog`

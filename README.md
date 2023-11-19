# github-clone-all-repos

A Python script designed to clone all public repositories of a specified GitHub user. This script is particularly useful for developers who want to quickly back up their GitHub repositories or analyze multiple repositories at once. We'll break down the script into its core components and explain the functionality and thought process behind each part.

Tags:
[[git]], [[github]], [[python]], [[automation]], [[scripting]], [[api]], [[git]], [[multi-threading]]


### Setting Up the Environment

The script begins by importing necessary modules and setting default values:

```python
import requests
from typing import List, Optional
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
import argparse
import time

try:
    from tqdm import tqdm
except ImportError:
    print(
        "Could not import tqdm. "
        "Run 'pip install tqdm' to enable progress bar."
    )
    tqdm = lambda x, *args, **kwargs: x

# Default values
DEFAULT_USERNAME: str = "magnus167"
DEFAULT_DIRECTORY: str = "./repos"
DEFAULT_TOKEN: Optional[str] = os.getenv("GH_TOKEN", None)
```

- **[Requests](https://docs.python-requests.org/en/latest/)**: Used for making HTTP requests to the GitHub API.
- **[OS](https://docs.python.org/3/library/os.html) & [Subprocess](https://docs.python.org/3/library/subprocess.html)**: For interacting with the operating system and executing shell commands.
- **[Concurrent.Futures](https://docs.python.org/3/library/concurrent.futures.html)**: Enables parallel execution of tasks, improving efficiency.
- **[Argparse](https://docs.python.org/3/library/argparse.html)**: For parsing command-line arguments.
- **[Time](https://docs.python.org/3/library/time.html)**: Used for implementing delays.

The script attempts to import `tqdm` for progress bar functionality. If `tqdm` is not installed, it falls back to a lambda function that simply returns the input without modification. This ensures that the script remains functional, albeit without progress bars, even if `tqdm` is not available.

- **[Tqdm](https://tqdm.github.io/)**: A fast, extensible progress bar for loops and CLI. The script checks for its presence and advises on installation if it's missing.

Default values for the GitHub username, directory for cloning repositories, and the GitHub token (sourced from an environment variable) are defined, providing a baseline configuration for the script.


## Fetching Public Repositories

The `get_public_repos` function retrieves all public repositories for a given GitHub user:

```python

def get_public_repos(username: str, pat_token: Optional[str] = None) -> List[str]:
    """
    Fetches the list of public repositories for a given GitHub username.

    :param username: GitHub username
    :param pat_token: Personal Access Token for GitHub API (optional)
    :return: List of repository clone URLs
    """
    print(f"Fetching public repos for {username}...")
    headers: dict = {"Authorization": f"token {pat_token}"} if pat_token else {}
    url: str = f"https://api.github.com/users/{username}/repos"
    response = requests.get(url, headers=headers)
    repos = response.json()
    return [repo["clone_url"] for repo in repos if not repo["private"]]

```

- It constructs a request to the GitHub API, optionally using a personal access token (PAT) for authentication.
- The response is parsed to extract clone URLs of public repositories.

## Cloning Repositories with Retries

The `run_git_clone` function attempts to clone a repository, retrying on failure:

```python

def run_git_clone(
    repo: str, directory: str, repo_name: str, max_retries: int = 5
) -> None:
    """
    Clones a repository with retries on failure.

    :param repo: Repository URL to clone
    :param directory: Directory to clone the repository into
    :param repo_name: Name of the repository
    :param max_retries: Maximum number of retries
    """
    while max_retries > 0:
        try:
            # Construct the command
            command = f"git clone {repo} {os.path.join(directory, repo_name)}/"
            null_device = "nul" if os.name == "nt" else "/dev/null"
            command += f" > {null_device} 2>&1"

            # Execute the command
            result = subprocess.run(command, shell=True, check=True)

            # Check if the command was successful
            if result.returncode == 0:
                return

        except subprocess.CalledProcessError as e:
            print(f"Error cloning {repo_name}: {e}")
            max_retries -= 1
            time.sleep(5)

    raise RuntimeError(f"Failed to clone {repo_name} after {max_retries} retries")


```

- It uses a `while` loop to retry the cloning process a specified number of times.
- The `subprocess.run` method executes the `git clone` command, redirecting output to null to keep the console clean.
- If cloning fails, it waits for 5 seconds before retrying.

## Cloning a Single Repository

The `clone_repo` function handles cloning of a single repository:

```python
def clone_repo(repo: str, directory: str) -> str:
    """
    Clones a single repository into a specified directory.

    :param repo: Repository URL to clone
    :param directory: Directory to clone the repository into
    :return: Name of the cloned repository
    """
    print(f"Cloning {repo}...")
    repo_name: str = repo.split("/")[-1].replace(
        ".git", ""
    )  # Extracts repo name from URL
    run_git_clone(repo, directory, repo_name)
    return repo_name


```

- It extracts the repository name from the URL and calls `run_git_clone`.
- This function is designed to be used with a thread pool for concurrent cloning.

## Cloning Multiple Repositories Concurrently

The `clone_repos` function orchestrates the cloning of multiple repositories:

```python

def clone_repos(
    repos: List[str],
    directory: str = "cloned_repos",
    show_progress: bool = False,
    n_threads: int = 5,
) -> None:
    """
    Clones a list of repositories using multiple threads.

    :param repos: List of repository URLs to clone
    :param directory: Directory to clone the repositories into
    :param show_progress: Whether to show a progress bar
    :param n_threads: Number of threads to use for cloning
    """
    if os.path.exists(directory):
        raise FileExistsError(f"Directory {directory} already exists.")
    else:
        os.makedirs(directory, exist_ok=True)

    with ThreadPoolExecutor(max_workers=n_threads) as executor:
        future_to_repo: dict = {}
        for repo in tqdm(
            repos,
            total=len(repos),
            desc="Cloning Repos",
            unit="repo",
            disable=not show_progress,
        ):
            future_to_repo[executor.submit(clone_repo, repo, directory)] = repo

        for future in tqdm(
            as_completed(future_to_repo),
            total=len(repos),
            desc="Cloning Repos",
            unit="repo",
            disable=not show_progress,
        ):
            repo_name: str = future_to_repo[future]
            try:
                future.result()
            except Exception as exc:
                print(f"{repo_name} generated an exception: {exc}")


```

- It checks if the target directory exists, creating it if necessary.
- A thread pool is set up to clone repositories in parallel, improving efficiency.
- Progress bars are displayed if enabled.

## Main Function and Command-Line Interface

The `main` function ties everything together:

```python


def main(
    username: str,
    directory: str,
    show_progress: bool = False,
    n_threads: int = 5,
    token: Optional[str] = None,
) -> None:
    """
    Main function to handle the cloning of GitHub repositories.

    :param username: GitHub username
    :param directory: Directory to clone the repositories into
    :param show_progress: Whether to show a progress bar
    :param n_threads: Number of threads to use for cloning
    :param token: Path to file containing a GitHub Personal Access Token
    """
    # Load token from file if provided
    if token:
        if token == "#ENV":
            token = DEFAULT_TOKEN
        else:
            if not os.path.exists(token):
                raise FileNotFoundError(f"Could not find file {token}.")
            with open(token, "r") as token_file:
                token = token_file.readline().strip()

    repos: List[str] = get_public_repos(username, token)
    clone_repos(repos, directory, show_progress, n_threads)


```

- It handles token loading (either from a file or an environment variable).
- Fetches the list of repositories and initiates the cloning process.

The script uses `argparse` to create a command-line interface, allowing users to specify parameters like username, directory, and token.

## Running the Script

Finally, the script is executed if run as the main program:

```python
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Clone all public repos of a GitHub user."
    )
    parser.add_argument(
        "-u",
        "--username",
        help="GitHub username to clone repos from.",
        type=str,
        default=DEFAULT_USERNAME,
    )
    parser.add_argument(
        "-d",
        "--directory",
        help="Directory to clone repos into.",
        type=str,
        default=DEFAULT_DIRECTORY,
    )
    parser.add_argument(
        "-p",
        "--show-progress",
        help="Set to False to hide the progress bar.",
        action="store_true",
    )
    parser.add_argument(
        "--n-threads",
        help="Number of threads to use for cloning repos.",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--token",
        help=(
            "File containing a GitHub Personal Access Token (PAT)."
            " #ENV to use GH_TOKEN env variable."
        ),
        type=str,
        default="#ENV",
    )

    args = parser.parse_args()
    main(
        username=args.username,
        directory=args.directory,
        show_progress=args.show_progress,
        n_threads=args.n_threads,
        token=args.token,
    )

```

This block parses command-line arguments and calls the `main` function with the appropriate arguments.

## Link to full script

The full script can be found [here](https://github.com/Magnus167/github-clone-all-repos/blob/main/clone-all.py) : [Magnu167/github-clone-all-repos](https://github.com/Magnus167/github-clone-all-repos)

## Conclusion

This Python script demonstrates a practical approach to automating the cloning of GitHub repositories. By leveraging Python's powerful libraries, it efficiently clones multiple repositories, handles potential errors, and provides a user-friendly command-line interface. Whether for backup, analysis, or migration purposes, this script offers a robust solution for managing GitHub repositories programmatically.

---

This markdown format should be easy to copy and use in a blog or documentation setting.
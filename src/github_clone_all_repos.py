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
    print("Could not import tqdm. Run 'pip install tqdm' to enable progress bar.")
    tqdm = lambda x, *args, **kwargs: x

# Default values
DEFAULT_USERNAME: str = "magnus167"
DEFAULT_DIRECTORY: str = "./repos"
DEFAULT_TOKEN: Optional[str] = os.getenv("GH_TOKEN", None)


def check_git_installed() -> None:
    """
    Checks if git is installed on the system.
    """
    try:
        subprocess.run("git --version", shell=True, check=True)
    except subprocess.CalledProcessError:
        raise RuntimeError(
            "Unable to find or run git. Please check installation or/and permissions."
        )

def get_public_repos(username: str, pat_token: Optional[str] = None, page_url: Optional[str] = None) -> List[str]:
    """
    Fetches the list of public repositories for a given GitHub username, accounting for pagination.

    :param username: GitHub username
    :param pat_token: Personal Access Token for GitHub API (optional)
    :param page_url: URL for the current page (used for recursion)
    :return: List of repository clone URLs
    """
    headers: dict = {"Authorization": f"token {pat_token}"} if pat_token else {}
    if page_url is None:
        url: str = f"https://api.github.com/users/{username}/repos"
    else:
        url = page_url

    response = requests.get(url, headers=headers)
    response_json = response.json()
    repos = [repo for repo in response_json if not repo["fork"]]
    if pat_token is None:
        repos = [repo for repo in repos if not repo["private"]]
    repo_urls = [repo["clone_url"] for repo in repos]

    # Check for 'next' page in the 'Link' header
    if 'next' in response.links:
        next_page_url = response.links['next']['url']
        repo_urls += get_public_repos(username, pat_token, next_page_url)

    return repo_urls


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
            time.sleep(1)

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

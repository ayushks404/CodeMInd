
from git import Repo
import os
import shutil

TMP_REPO_PATH = "./tmp/repos"

def clone_repo(repo_url: str, project_id: str) -> str:
    path = os.path.join(TMP_REPO_PATH, project_id)

    if os.path.exists(path):
        shutil.rmtree(path)

    os.makedirs(path, exist_ok=True)
    Repo.clone_from(repo_url, path)
    return path

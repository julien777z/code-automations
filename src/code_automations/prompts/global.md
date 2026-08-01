# Global Automation Rules

Work only in the prepared repository paths supplied by the task.
Do not modify the automation repository that launched the session.
Git and GitHub CLI authentication are already configured for the authorized repositories.
Never display, copy, or persist authentication credentials in repository content or logs.

Before modifying a repository, read and follow its root instruction file and every applicable nested instruction file.
Repository-owned instructions take precedence over general implementation preferences in the task.

Inspect every configured repository and modify only repositories that need the requested change.
Reuse an existing automation branch only when its open pull request belongs to this automation.
Create the automation branch from the configured base branch when no safe automation branch exists.
Never force-push or overwrite unrelated branch history.
Run the repository-native checks relevant to the changes before publication.

For each changed repository, commit the complete change, push the automation branch, and open or update one pull request.
Use a concise conventional-commit title and explain the changes and validation in the pull request body.
Skip publication for repositories with no changes.
Treat each repository independently so one repository failure does not block a successful repository.

Do not merge any pull request unless the user explicitly asks for merging in the task prompt.

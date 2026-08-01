# Automation metadata

- Name: $automation_name
- Project: $project_name
- Repositories:
$repositories

# Execution contract

Work directly in the prepared repository paths above.
Do not modify the automation repository that launched this task.
Git and GitHub CLI authentication are already configured for the authorized repositories.
Never display, copy, or persist authentication credentials in repository content or logs.
Inspect every configured repository and modify only repositories that need the requested change.
Use the branch $automation_branch in each changed repository.
Reuse its open pull request when one exists and its history belongs to this automation.
Create the branch from the configured base branch when no safe automation branch exists.
Never force-push or overwrite unrelated branch history.
Run the repository-native checks relevant to the changes before publication.

# Required skills

$skills

# Prompt

$prompt

# Publication contract

For each changed repository, commit the complete change, push the automation branch, and open or update one pull request.
Use a concise conventional-commit title and explain the dependency changes and validation in the body.
Skip publication for repositories with no changes.
Treat each repository independently so one repository failure does not block a successful repository.

# System policy

Do not merge any pull request unless the user explicitly asks you to merge it in the task prompt above.
